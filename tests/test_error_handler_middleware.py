"""Tests for the error handler middleware."""

import pytest
from fastmcp import Context
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_search_hub.middleware.error_handler import ErrorHandlerMiddleware
from mcp_search_hub.utils.errors import (
    AuthenticationError,
    ProviderRateLimitError,
    SearchError,
)


@pytest.fixture
def error_handler_middleware():
    """Create an instance of ErrorHandlerMiddleware for testing."""
    return ErrorHandlerMiddleware()


@pytest.mark.asyncio
async def test_pass_through_success(error_handler_middleware):
    """Test that the middleware passes through successful responses."""
    # Mock request and response
    request = {"key": "value"}
    expected_response = {"result": "success"}

    # Mock call_next function
    async def call_next(_):
        return expected_response

    # Process the request through middleware
    response = await error_handler_middleware(request, call_next)

    # Verify the response is passed through unchanged
    assert response == expected_response


@pytest.mark.asyncio
async def test_format_search_error(error_handler_middleware):
    """Test handling of SearchError for tool requests."""
    # Mock request
    request = {"tool_name": "test_tool", "query": "test"}
    context = Context()

    # Create a search error
    error = SearchError(
        message="Test error",
        provider="test_provider",
        status_code=400,
        details={"key": "value"},
    )

    # Mock call_next function that raises the error
    async def call_next(_):
        raise error

    # Process the request through middleware
    result = await error_handler_middleware(request, call_next, context)

    # Verify the error is formatted correctly
    assert isinstance(result, dict)
    assert result["error_type"] == "SearchError"
    assert result["message"] == "Test error"
    assert result["provider"] == "test_provider"
    assert result["details"]["key"] == "value"


@pytest.mark.asyncio
async def test_format_authentication_error_http(error_handler_middleware):
    """Test handling of AuthenticationError for HTTP requests."""
    # Mock HTTP request
    request = Request({"type": "http", "method": "GET", "path": "/test"})

    # Create an authentication error
    error = AuthenticationError(message="Invalid API key")

    # Mock call_next function that raises the error
    async def call_next(_):
        raise error

    # Process the request through middleware
    response = await error_handler_middleware(request, call_next)

    # Verify the response is a proper JSONResponse
    assert isinstance(response, JSONResponse)
    assert response.status_code == 401

    # Check content
    content = response.body.decode("utf-8")
    assert "Invalid API key" in content
    assert "AuthenticationError" in content


@pytest.mark.asyncio
async def test_format_rate_limit_error_with_headers(error_handler_middleware):
    """Test handling of ProviderRateLimitError with custom headers."""
    # Mock HTTP request
    request = Request({"type": "http", "method": "GET", "path": "/test"})

    # Create a rate limit error with custom headers
    error = ProviderRateLimitError(
        provider="test_provider",
        limit_type="requests_per_minute",
        retry_after=30,
        message="Rate limit exceeded",
    )

    # Add headers to error details
    error.details["headers"] = {
        "X-RateLimit-Limit": "100",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "30",
        "Retry-After": "30",
    }

    # Mock call_next function that raises the error
    async def call_next(_):
        raise error

    # Process the request through middleware
    response = await error_handler_middleware(request, call_next)

    # Verify the response is a proper JSONResponse with the headers
    assert isinstance(response, JSONResponse)
    assert response.status_code == 429
    assert response.headers["X-RateLimit-Limit"] == "100"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["X-RateLimit-Reset"] == "30"
    assert response.headers["Retry-After"] == "30"

    # Check content
    content = response.body.decode("utf-8")
    assert "Rate limit exceeded" in content
    assert "ProviderRateLimitError" in content


@pytest.mark.asyncio
async def test_format_generic_exception(error_handler_middleware):
    """Test handling of a generic Exception."""
    # Mock request
    request = {"tool_name": "test_tool", "query": "test"}

    # Mock call_next function that raises a generic error
    async def call_next(_):
        raise ValueError("Invalid value")

    # Process the request through middleware
    result = await error_handler_middleware(request, call_next)

    # Verify the error is formatted correctly
    assert isinstance(result, dict)
    assert result["error"] == "Invalid value"
    assert result["type"] == "ValueError"


@pytest.mark.asyncio
async def test_middleware_order(error_handler_middleware):
    """Test that error handler middleware has very low order value."""
    # It should run first (last in the chain) to catch errors from all other middleware
    assert error_handler_middleware.order == 0
