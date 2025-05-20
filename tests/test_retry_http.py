"""Tests for retry functionality with real HTTP interactions."""

import asyncio
from typing import Any

import httpx
import pytest
import respx

# Skip FastAPI tests if not installed
try:
    from fastapi import FastAPI, Request, Response
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from mcp_search_hub.utils.retry import RetryConfig, with_exponential_backoff


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestRetryWithMockServer:
    """Test retry functionality with a mock HTTP server."""

    @pytest.fixture
    def app(self):
        """Create a FastAPI app for testing."""
        app = FastAPI()

        # Track request attempts
        app.state.request_count = {}
        app.state.fail_count = {}

        @app.get("/always-success")
        async def always_success():
            """Endpoint that always succeeds."""
            req_id = "success"
            app.state.request_count[req_id] = app.state.request_count.get(req_id, 0) + 1
            return {"status": "success"}

        @app.get("/always-fail")
        async def always_fail():
            """Endpoint that always fails with 503."""
            req_id = "fail"
            app.state.request_count[req_id] = app.state.request_count.get(req_id, 0) + 1
            return Response(status_code=503, content="Service Unavailable")

        @app.get("/fail-then-succeed/{fail_count}")
        async def fail_then_succeed(fail_count: int):
            """Endpoint that fails a specified number of times, then succeeds."""
            req_id = f"fail-{fail_count}"
            # Initialize failure count if first request
            if req_id not in app.state.fail_count:
                app.state.fail_count[req_id] = 0

            # Count the request
            app.state.request_count[req_id] = app.state.request_count.get(req_id, 0) + 1

            # Fail if we haven't reached the fail count
            if app.state.fail_count[req_id] < fail_count:
                app.state.fail_count[req_id] += 1
                return Response(status_code=503, content="Service Unavailable")

            # Otherwise succeed
            return {"status": "success", "attempts": app.state.request_count[req_id]}

        @app.get("/mixed-failures")
        async def mixed_failures(request: Request):
            """Endpoint that returns different status codes based on an X-Failure-Type header."""
            req_id = "mixed"
            app.state.request_count[req_id] = app.state.request_count.get(req_id, 0) + 1

            # Get failure type from header
            failure_type = request.headers.get("X-Failure-Type", "success")

            if failure_type == "timeout":
                # Wait longer than client timeout
                await asyncio.sleep(3)
                return {"status": "never reached"}
            if failure_type == "rate_limit":
                return Response(
                    status_code=429,
                    content="Too Many Requests",
                    headers={"Retry-After": "1"},
                )
            if failure_type == "server_error":
                return Response(status_code=500, content="Internal Server Error")
            if failure_type == "bad_gateway":
                return Response(status_code=502, content="Bad Gateway")
            if failure_type == "client_error":
                # Non-retryable client error
                return Response(status_code=400, content="Bad Request")
            return {"status": "success"}

        return app

    @pytest.fixture
    def client(self, app):
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_successful_request_no_retry(self, app, client):
        """Test that a successful request doesn't trigger retries."""

        @with_exponential_backoff(RetryConfig(max_retries=3, base_delay=0.01))
        async def fetch_success():
            async with httpx.AsyncClient(
                app=app, base_url="http://test"
            ) as http_client:
                response = await http_client.get("/always-success")
                response.raise_for_status()
                return response.json()

        result = await fetch_success()
        assert result == {"status": "success"}
        assert app.state.request_count.get("success", 0) == 1  # Only called once

    @pytest.mark.asyncio
    async def test_always_failing_request_retries_and_fails(self, app, client):
        """Test that a failing request retries the configured number of times then fails."""

        @with_exponential_backoff(RetryConfig(max_retries=2, base_delay=0.01))
        async def fetch_failing():
            async with httpx.AsyncClient(
                app=app, base_url="http://test"
            ) as http_client:
                response = await http_client.get("/always-fail")
                response.raise_for_status()
                return response.json()

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await fetch_failing()

        assert exc_info.value.response.status_code == 503
        assert app.state.request_count.get("fail", 0) == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_fail_then_succeed(self, app, client):
        """Test a request that fails twice then succeeds on the third attempt."""

        @with_exponential_backoff(RetryConfig(max_retries=3, base_delay=0.01))
        async def fetch_eventually_succeeding():
            async with httpx.AsyncClient(
                app=app, base_url="http://test"
            ) as http_client:
                response = await http_client.get("/fail-then-succeed/2")
                response.raise_for_status()
                return response.json()

        result = await fetch_eventually_succeeding()
        assert result["status"] == "success"
        assert result["attempts"] == 3  # 2 failures + 1 success
        assert app.state.request_count.get("fail-2", 0) == 3

    @pytest.mark.asyncio
    async def test_timeout_retries(self, app):
        """Test retries with timeout errors."""

        @with_exponential_backoff(RetryConfig(max_retries=2, base_delay=0.01))
        async def fetch_with_timeout():
            # Need a very short timeout to trigger timeout errors
            async with httpx.AsyncClient(
                app=app, base_url="http://test", timeout=0.1
            ) as http_client:
                response = await http_client.get(
                    "/mixed-failures", headers={"X-Failure-Type": "timeout"}
                )
                response.raise_for_status()
                return response.json()

        with pytest.raises(httpx.TimeoutException):
            await fetch_with_timeout()

        assert app.state.request_count.get("mixed", 0) == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_various_server_errors(self, app):
        """Test retries with various server error status codes."""
        failure_types = ["rate_limit", "server_error", "bad_gateway"]
        retry_config = RetryConfig(max_retries=1, base_delay=0.01)

        # Helper function to test a specific failure type
        async def test_failure_type(failure_type):
            app.state.request_count = {}  # Reset counters

            @with_exponential_backoff(retry_config)
            async def fetch_server_error():
                async with httpx.AsyncClient(
                    app=app, base_url="http://test"
                ) as http_client:
                    response = await http_client.get(
                        "/mixed-failures",
                        headers={"X-Failure-Type": failure_type},
                    )
                    response.raise_for_status()
                    return response.json()

            with pytest.raises(httpx.HTTPStatusError):
                await fetch_server_error()

            # Should be called twice for each error type (initial + 1 retry)
            assert app.state.request_count.get("mixed", 0) == 2

        # Test each failure type
        for failure_type in failure_types:
            await test_failure_type(failure_type)

    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self, app):
        """Test that client errors (4xx except 429) don't trigger retries."""

        @with_exponential_backoff(RetryConfig(max_retries=2, base_delay=0.01))
        async def fetch_client_error():
            async with httpx.AsyncClient(
                app=app, base_url="http://test"
            ) as http_client:
                response = await http_client.get(
                    "/mixed-failures", headers={"X-Failure-Type": "client_error"}
                )
                response.raise_for_status()
                return response.json()

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await fetch_client_error()

        assert exc_info.value.response.status_code == 400
        assert app.state.request_count.get("mixed", 0) == 1  # No retries


class TestRetryWithRespx:
    """Test retry functionality with respx mocking library."""

    @pytest.mark.asyncio
    async def test_retry_with_multiple_urls(self):
        """Test retry with requests to multiple URLs."""
        with respx.mock:
            # Set up mock routes
            route1 = respx.get("https://api.example.com/endpoint1").mock(
                return_value=httpx.Response(
                    429,
                    headers={"Retry-After": "1", "Content-Type": "application/json"},
                )
            )
            route2 = respx.get("https://api.example.com/endpoint2").mock(
                return_value=httpx.Response(503)
            )
            route3 = respx.get("https://api.example.com/endpoint3").mock(
                return_value=httpx.Response(
                    200,
                    json={"status": "success"},
                    headers={"Content-Type": "application/json"},
                )
            )

            @with_exponential_backoff(RetryConfig(max_retries=1, base_delay=0.01))
            async def fetch_multiple():
                results: dict[str, Any] = {}
                async with httpx.AsyncClient() as client:
                    # Will fail with 429, should retry
                    try:
                        response1 = await client.get(
                            "https://api.example.com/endpoint1"
                        )
                        response1.raise_for_status()
                        results["endpoint1"] = response1.json()
                    except httpx.HTTPStatusError:
                        results["endpoint1"] = "failed"

                    # Will fail with 503, should retry
                    try:
                        response2 = await client.get(
                            "https://api.example.com/endpoint2"
                        )
                        response2.raise_for_status()
                        results["endpoint2"] = response2.json()
                    except httpx.HTTPStatusError:
                        results["endpoint2"] = "failed"

                    # Will succeed
                    response3 = await client.get("https://api.example.com/endpoint3")
                    response3.raise_for_status()
                    results["endpoint3"] = response3.json()

                    return results

            results = await fetch_multiple()

            # Verify number of calls to each endpoint
            assert route1.call_count == 2  # Initial + 1 retry
            assert route2.call_count == 2  # Initial + 1 retry
            assert route3.call_count == 1  # No retries needed

            # Verify results
            assert results["endpoint1"] == "failed"
            assert results["endpoint2"] == "failed"
            assert results["endpoint3"] == {"status": "success"}

    @pytest.mark.asyncio
    async def test_retry_sequence(self):
        """Test retry with a sequence of responses."""
        with respx.mock:
            # Configure route to return different responses on subsequent requests
            route = respx.get("https://api.example.com/sequence").mock(
                side_effect=[
                    httpx.Response(500),  # First call: 500 error
                    httpx.Response(429),  # Second call: 429 error
                    httpx.Response(
                        200, json={"result": "success"}
                    ),  # Third call: success
                ]
            )

            @with_exponential_backoff(RetryConfig(max_retries=2, base_delay=0.01))
            async def fetch_sequence():
                async with httpx.AsyncClient() as client:
                    response = await client.get("https://api.example.com/sequence")
                    response.raise_for_status()
                    return response.json()

            result = await fetch_sequence()
            assert result == {"result": "success"}
            assert route.call_count == 3  # All three responses in the sequence

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests(self):
        """Test retry with multiple concurrent requests."""
        with respx.mock:
            # Configure routes for three different endpoints
            routes = {
                "endpoint1": respx.get("https://api.example.com/endpoint1").mock(
                    side_effect=[
                        httpx.Response(500),  # First call: error
                        httpx.Response(200, json={"id": 1}),  # Second call: success
                    ]
                ),
                "endpoint2": respx.get("https://api.example.com/endpoint2").mock(
                    side_effect=[
                        httpx.Response(500),  # First call: error
                        httpx.Response(500),  # Second call: error
                        httpx.Response(200, json={"id": 2}),  # Third call: success
                    ]
                ),
                "endpoint3": respx.get("https://api.example.com/endpoint3").mock(
                    return_value=httpx.Response(200, json={"id": 3})  # Always succeeds
                ),
            }

            # Define a function to fetch from a specific endpoint
            async def fetch_endpoint(url):
                @with_exponential_backoff(RetryConfig(max_retries=2, base_delay=0.01))
                async def _fetch():
                    async with httpx.AsyncClient() as client:
                        response = await client.get(url)
                        response.raise_for_status()
                        return response.json()

                return await _fetch()

            # Run requests concurrently
            results = await asyncio.gather(
                fetch_endpoint("https://api.example.com/endpoint1"),
                fetch_endpoint("https://api.example.com/endpoint2"),
                fetch_endpoint("https://api.example.com/endpoint3"),
            )

            # Check results from all endpoints
            assert results == [{"id": 1}, {"id": 2}, {"id": 3}]

            # Verify call counts
            assert routes["endpoint1"].call_count == 2  # 1 retry
            assert routes["endpoint2"].call_count == 3  # 2 retries
            assert routes["endpoint3"].call_count == 1  # No retries
