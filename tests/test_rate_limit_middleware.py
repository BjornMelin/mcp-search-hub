"""Tests for rate limiting middleware."""

import asyncio
import time
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import Response

from mcp_search_hub.middleware.rate_limit import RateLimiter, RateLimitMiddleware


class TestRateLimiter:
    """Test cases for the RateLimiter class."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(limit=10, window=60)

        assert limiter.limit == 10
        assert limiter.window == 60
        assert limiter.requests == []
        assert limiter._lock is not None

    @pytest.mark.asyncio
    async def test_check_rate_limit_allowed(self):
        """Test rate limiter allows requests under the limit."""
        limiter = RateLimiter(limit=3, window=60)

        # First request
        allowed, remaining, reset = await limiter.check_rate_limit("test_client")
        assert allowed is True
        assert remaining == 2
        assert reset == 60

        # Second request
        allowed, remaining, reset = await limiter.check_rate_limit("test_client")
        assert allowed is True
        assert remaining == 1
        assert reset == 60

        # Third request
        allowed, remaining, reset = await limiter.check_rate_limit("test_client")
        assert allowed is True
        assert remaining == 0
        assert reset == 60

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self):
        """Test rate limiter blocks requests over the limit."""
        limiter = RateLimiter(limit=2, window=60)

        # First request
        await limiter.check_rate_limit("test_client")

        # Second request
        await limiter.check_rate_limit("test_client")

        # Third request (should be blocked)
        allowed, remaining, reset = await limiter.check_rate_limit("test_client")
        assert allowed is False
        assert remaining == 0
        assert reset > 0  # Should have some time until reset

    @pytest.mark.asyncio
    async def test_cleanup_expired_requests(self):
        """Test rate limiter cleans up expired requests."""
        limiter = RateLimiter(limit=2, window=1)  # 1 second window

        # Add a request with an old timestamp
        limiter.requests = [time.time() - 2]  # 2 seconds ago

        # Make a new request
        allowed, remaining, reset = await limiter.check_rate_limit("test_client")

        # The old request should be cleaned up
        assert allowed is True
        assert remaining == 1
        assert len(limiter.requests) == 1  # Only the new request remains

    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test rate limiter handles concurrent requests correctly."""
        limiter = RateLimiter(limit=10, window=60)

        # Run 10 concurrent requests
        results = await asyncio.gather(
            *[limiter.check_rate_limit(f"client_{i}") for i in range(10)]
        )

        # All should be allowed
        assert all(allowed for allowed, _, _ in results)

        # The 11th request should be blocked
        allowed, remaining, reset = await limiter.check_rate_limit("extra")
        assert allowed is False
        assert remaining == 0


class TestRateLimitMiddleware:
    """Test cases for the RateLimitMiddleware class."""

    def test_initialization_default(self):
        """Test middleware initialization with default values."""
        middleware = RateLimitMiddleware()

        assert middleware.order == 20  # Default order
        assert middleware.limit == 100  # Default limit
        assert middleware.window == 60  # Default window
        assert middleware.skip_paths == ["/health", "/metrics"]
        assert middleware.global_limiter.limit == 1000
        assert middleware.global_limiter.window == 60

    def test_initialization_custom(self):
        """Test middleware initialization with custom values."""
        middleware = RateLimitMiddleware(
            order=30,
            limit=50,
            window=120,
            global_limit=500,
            global_window=30,
            skip_paths=["/skip1", "/skip2"],
        )

        assert middleware.order == 30
        assert middleware.limit == 50
        assert middleware.window == 120
        assert middleware.skip_paths == ["/skip1", "/skip2"]
        assert middleware.global_limiter.limit == 500
        assert middleware.global_limiter.window == 30

    def test_get_client_id_from_ip(self):
        """Test extracting client ID from IP address."""
        middleware = RateLimitMiddleware()

        # Mock request with client IP
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.1"

        client_id = middleware._get_client_id(mock_request)
        assert client_id == "192.168.1.1"

    def test_get_client_id_from_forwarded_ip(self):
        """Test extracting client ID from X-Forwarded-For header."""
        middleware = RateLimitMiddleware()

        # Mock request with X-Forwarded-For
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-Forwarded-For": "10.0.0.1, 10.0.0.2"}

        client_id = middleware._get_client_id(mock_request)
        assert client_id == "10.0.0.1"  # Should use the first IP

    def test_get_client_id_from_api_key(self):
        """Test extracting client ID from API key."""
        middleware = RateLimitMiddleware()

        # Mock request with API key
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-API-Key": "abcdef123456789"}

        client_id = middleware._get_client_id(mock_request)
        assert client_id == "abcdef12"  # First 8 chars

        # Test with Bearer token
        mock_request.headers = {"Authorization": "Bearer xyz987654321"}
        client_id = middleware._get_client_id(mock_request)
        assert client_id == "xyz98765"

    def test_get_client_id_for_tool_request(self):
        """Test client ID for tool requests."""
        middleware = RateLimitMiddleware()

        # For non-Request objects, should return "tool"
        client_id = middleware._get_client_id({"param": "value"})
        assert client_id == "tool"

    @pytest.mark.asyncio
    async def test_process_request_non_http(self):
        """Test processing non-HTTP requests (should pass through)."""
        middleware = RateLimitMiddleware()

        # Tool request
        tool_request = {"param": "value"}
        result = await middleware.process_request(tool_request)
        assert result == tool_request

    @pytest.mark.asyncio
    async def test_process_request_skipped_path(self):
        """Test processing request for path that skips rate limiting."""
        middleware = RateLimitMiddleware(skip_paths=["/health", "/skip"])

        # Create mock request with skipped path
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/health"

        result = await middleware.process_request(mock_request)
        assert result == mock_request

    @pytest.mark.asyncio
    async def test_process_request_under_limit(self):
        """Test processing request under the rate limit."""
        middleware = RateLimitMiddleware(limit=10)

        # Mock the rate limiters to always allow
        middleware.global_limiter.check_rate_limit = AsyncMock(
            return_value=(True, 9, 60)
        )
        test_limiter = MagicMock()
        test_limiter.check_rate_limit = AsyncMock(return_value=(True, 9, 60))
        middleware.limiters = defaultdict(lambda: test_limiter)

        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/search"
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.1"

        result = await middleware.process_request(mock_request)
        assert result == mock_request

    @pytest.mark.asyncio
    async def test_process_request_global_limit_exceeded(self):
        """Test processing request that exceeds global rate limit."""
        middleware = RateLimitMiddleware()

        # Mock global limiter to reject
        middleware.global_limiter.check_rate_limit = AsyncMock(
            return_value=(False, 0, 30)
        )

        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/search"
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.1"

        # Should raise exception with JSONResponse
        with pytest.raises(Exception, match="Rate limit exceeded"):
            await middleware.process_request(mock_request)

    @pytest.mark.asyncio
    async def test_process_request_client_limit_exceeded(self):
        """Test processing request that exceeds client rate limit."""
        middleware = RateLimitMiddleware()

        # Mock global limiter to allow but client limiter to reject
        middleware.global_limiter.check_rate_limit = AsyncMock(
            return_value=(True, 999, 60)
        )

        # Create a test client limiter
        test_limiter = MagicMock()
        test_limiter.check_rate_limit = AsyncMock(return_value=(False, 0, 15))
        test_limiter.limit = 10
        middleware.limiters = defaultdict(lambda: test_limiter)

        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/search"
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.1"

        # Should raise exception with JSONResponse
        with pytest.raises(Exception, match="Rate limit exceeded"):
            await middleware.process_request(mock_request)

    @pytest.mark.asyncio
    async def test_process_response_non_http(self):
        """Test processing non-HTTP responses (should pass through)."""
        middleware = RateLimitMiddleware()

        # Non-HTTP response
        response = {"result": "success"}
        result = await middleware.process_response(response, {})
        assert result == response

    @pytest.mark.asyncio
    async def test_process_response_skipped_path(self):
        """Test processing response for skipped path."""
        middleware = RateLimitMiddleware(skip_paths=["/health"])

        # Create mock request and response
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/health"
        mock_response = MagicMock(spec=Response)
        mock_response.headers = {}

        result = await middleware.process_response(mock_response, mock_request)
        assert result == mock_response
        assert "X-RateLimit-Limit" not in mock_response.headers

    @pytest.mark.asyncio
    async def test_process_response_adds_headers(self):
        """Test processing response adds rate limit headers."""
        middleware = RateLimitMiddleware(limit=100)

        # Create test limiter
        test_limiter = MagicMock()
        test_limiter.limit = 100
        test_limiter.window = 60
        test_limiter.requests = [time.time()] * 5  # 5 recent requests
        middleware.limiters = defaultdict(lambda: test_limiter)

        # Create mock request and response
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/search"
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.1"

        mock_response = MagicMock(spec=Response)
        mock_response.headers = {}

        # Process response
        result = await middleware.process_response(mock_response, mock_request)

        # Check headers
        assert result == mock_response
        assert mock_response.headers["X-RateLimit-Limit"] == "100"
        assert mock_response.headers["X-RateLimit-Remaining"] == "95"  # 100 - 5
        assert "X-RateLimit-Reset" in mock_response.headers


@pytest.mark.asyncio
async def test_integration_with_multiple_clients():
    """Test rate limiting for multiple clients."""
    # Create middleware with low limits for testing
    middleware = RateLimitMiddleware(limit=2, window=60)

    # Create mock requests for different clients
    client1_req = MagicMock(spec=Request)
    client1_req.url.path = "/search"
    client1_req.headers = {"X-API-Key": "client1-key"}
    client1_req.client = None

    client2_req = MagicMock(spec=Request)
    client2_req.url.path = "/search"
    client2_req.headers = {"X-API-Key": "client2-key"}
    client2_req.client = None

    # First request from client1
    result1 = await middleware.process_request(client1_req)
    assert result1 == client1_req

    # First request from client2
    result2 = await middleware.process_request(client2_req)
    assert result2 == client2_req

    # Second request from client1
    result3 = await middleware.process_request(client1_req)
    assert result3 == client1_req

    # Third request from client1 should be blocked
    with pytest.raises(Exception, match="Rate limit exceeded"):
        await middleware.process_request(client1_req)

    # But client2 should still be allowed
    result4 = await middleware.process_request(client2_req)
    assert result4 == client2_req
