"""Tests for RetryMiddleware."""

from unittest.mock import MagicMock

import httpx
import pytest
from fastmcp import Context
from starlette.requests import Request
from starlette.responses import Response

from mcp_search_hub.middleware.retry import RetryMiddleware
from mcp_search_hub.utils.errors import ProviderTimeoutError


@pytest.fixture
def retry_middleware():
    """Return a RetryMiddleware instance."""
    return RetryMiddleware(
        enabled=True,
        max_retries=3,
        base_delay=0.01,  # Very short delay for testing
        jitter=False,  # Disable jitter for deterministic tests
    )


@pytest.fixture
def mock_request():
    """Return a mock starlette Request."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/search",
        "headers": [(b"content-type", b"application/json")],
    }
    return Request(scope=scope)


@pytest.fixture
def mock_tool_params():
    """Return mock tool parameters."""
    return {"query": "test", "tool_name": "search"}


@pytest.fixture
def mock_context():
    """Return a mock Context object."""
    return MagicMock(spec=Context)


class TestRetryMiddleware:
    """Tests for the RetryMiddleware class."""

    @pytest.mark.asyncio
    async def test_process_request(
        self, retry_middleware, mock_request, mock_tool_params
    ):
        """Test process_request method."""
        # For HTTP request
        processed_request = await retry_middleware.process_request(mock_request)
        assert processed_request == mock_request
        assert hasattr(processed_request.state, "retry_attempt")
        assert processed_request.state.retry_attempt == 0
        assert hasattr(processed_request.state, "retryable_request")
        assert processed_request.state.retryable_request is True

        # For tool params
        processed_params = await retry_middleware.process_request(mock_tool_params)
        assert processed_params != mock_tool_params  # Should be a copy
        assert "_retry_attempt" in processed_params
        assert processed_params["_retry_attempt"] == 0
        assert "_retryable_request" in processed_params
        assert processed_params["_retryable_request"] is True

    @pytest.mark.asyncio
    async def test_process_response(
        self, retry_middleware, mock_request, mock_tool_params
    ):
        """Test process_response method."""
        response = Response(content="Test")
        processed_response = await retry_middleware.process_response(
            response, mock_request
        )
        assert processed_response == response

    @pytest.mark.asyncio
    async def test_calculate_delay(self, retry_middleware):
        """Test calculate_delay method."""
        # First attempt
        assert retry_middleware.calculate_delay(0) == 0.01  # base_delay

        # Second attempt
        assert (
            retry_middleware.calculate_delay(1) == 0.02
        )  # base_delay * (exponential_base ** 1)

        # Third attempt
        assert (
            retry_middleware.calculate_delay(2) == 0.04
        )  # base_delay * (exponential_base ** 2)

    @pytest.mark.asyncio
    async def test_is_retryable_exception(self, retry_middleware):
        """Test is_retryable_exception method."""
        # Retryable exceptions
        assert retry_middleware.is_retryable_exception(
            httpx.TimeoutException("timeout")
        )
        assert retry_middleware.is_retryable_exception(
            httpx.ConnectError("connect error")
        )
        assert retry_middleware.is_retryable_exception(
            ConnectionError("connection error")
        )
        assert retry_middleware.is_retryable_exception(
            ProviderTimeoutError("provider timeout", "test")
        )

        # HTTP status errors
        mock_response = MagicMock()
        mock_response.status_code = 429
        assert retry_middleware.is_retryable_exception(
            httpx.HTTPStatusError("", request=MagicMock(), response=mock_response)
        )

        mock_response.status_code = 500
        assert retry_middleware.is_retryable_exception(
            httpx.HTTPStatusError("", request=MagicMock(), response=mock_response)
        )

        # Non-retryable exceptions
        assert not retry_middleware.is_retryable_exception(ValueError("value error"))
        mock_response.status_code = 400
        assert not retry_middleware.is_retryable_exception(
            httpx.HTTPStatusError("", request=MagicMock(), response=mock_response)
        )

    @pytest.mark.asyncio
    async def test_should_retry_request(self, retry_middleware, mock_request):
        """Test should_retry_request method."""
        # Normal request should be retried
        assert retry_middleware.should_retry_request(mock_request) is True

        # Create a request with a skipped path
        skip_scope = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [(b"content-type", b"application/json")],
        }
        skip_request = Request(scope=skip_scope)
        assert retry_middleware.should_retry_request(skip_request) is False

        # Tool requests should always be retried
        assert retry_middleware.should_retry_request({"tool_name": "search"}) is True

    @pytest.mark.asyncio
    async def test_successful_call(self, retry_middleware, mock_request, mock_context):
        """Test middleware with successful call."""

        # Mock call_next function that succeeds
        async def call_next(req):
            return Response(content="Success")

        # Call middleware
        response = await retry_middleware(mock_request, call_next, mock_context)
        assert response.body == b"Success"

    @pytest.mark.asyncio
    async def test_retry_on_retryable_exception(
        self, retry_middleware, mock_request, mock_context
    ):
        """Test middleware with retryable exception."""
        call_count = 0

        # Mock call_next that fails twice then succeeds
        async def call_next(req):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("Timeout")
            return Response(content="Success after retry")

        # Call middleware
        response = await retry_middleware(mock_request, call_next, mock_context)
        assert response.body == b"Success after retry"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable_exception(
        self, retry_middleware, mock_request, mock_context
    ):
        """Test middleware with non-retryable exception."""

        # Mock call_next that fails with non-retryable exception
        async def call_next(req):
            raise ValueError("Non-retryable error")

        # Call middleware
        with pytest.raises(ValueError, match="Non-retryable error"):
            await retry_middleware(mock_request, call_next, mock_context)

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(
        self, retry_middleware, mock_request, mock_context
    ):
        """Test middleware with max retries exhausted."""

        # Mock call_next that always fails with retryable exception
        async def call_next(req):
            raise httpx.TimeoutException("Always timeout")

        # Call middleware
        with pytest.raises(httpx.TimeoutException, match="Always timeout"):
            await retry_middleware(mock_request, call_next, mock_context)

    @pytest.mark.asyncio
    async def test_skip_path(self, retry_middleware, mock_context):
        """Test middleware with skipped path."""
        # Create a request with skipped path
        skip_scope = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [(b"content-type", b"application/json")],
        }
        skip_request = Request(scope=skip_scope)

        call_count = 0

        # Mock call_next that would fail if called more than once
        async def call_next(req):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise httpx.TimeoutException("This should not be retried")
            return Response(content="Success without retry")

        # Call middleware
        response = await retry_middleware(skip_request, call_next, mock_context)
        assert response.body == b"Success without retry"
        assert call_count == 1  # Should not retry for skipped paths

    @pytest.mark.asyncio
    async def test_tool_params_retry(
        self, retry_middleware, mock_tool_params, mock_context
    ):
        """Test middleware with tool parameters."""
        call_count = 0

        # Mock call_next that fails twice then succeeds
        async def call_next(params):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("Timeout")
            return {"result": "Success"}

        # Call middleware
        result = await retry_middleware(mock_tool_params, call_next, mock_context)
        assert result == {"result": "Success"}
        assert call_count == 3
