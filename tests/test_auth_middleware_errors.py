"""Tests for authentication middleware error handling."""

import pytest
from fastmcp import Context
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_search_hub.middleware.auth import AuthMiddleware
from mcp_search_hub.utils.errors import AuthenticationError, http_error_response


@pytest.fixture
def auth_middleware():
    """Create an instance of AuthMiddleware with test API keys."""
    return AuthMiddleware(api_keys=["test-key-1", "test-key-2"])


@pytest.mark.asyncio
async def test_auth_middleware_valid_key(auth_middleware):
    """Test that the middleware passes through requests with valid API keys."""
    # Create mock request with valid API key
    mock_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/search",
            "headers": [(b"x-api-key", b"test-key-1")],
        }
    )

    # Process request - should pass through without exception
    result = await auth_middleware.process_request(mock_request)
    assert result == mock_request


@pytest.mark.asyncio
async def test_auth_middleware_invalid_key(auth_middleware):
    """Test that the middleware raises AuthenticationError for invalid API keys."""
    # Create mock request with invalid API key
    mock_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/search",
            "headers": [(b"x-api-key", b"invalid-key")],
        }
    )

    # Process request - should raise AuthenticationError
    with pytest.raises(AuthenticationError) as exc_info:
        await auth_middleware.process_request(mock_request)

    # Verify error details
    assert "Invalid or missing API key" in str(exc_info.value)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_middleware_missing_key(auth_middleware):
    """Test that the middleware raises AuthenticationError for missing API keys."""
    # Create mock request with no API key
    mock_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/search",
            "headers": [],
        }
    )

    # Process request - should raise AuthenticationError
    with pytest.raises(AuthenticationError) as exc_info:
        await auth_middleware.process_request(mock_request)

    # Verify error details
    assert "Invalid or missing API key" in str(exc_info.value)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_middleware_bearer_key(auth_middleware):
    """Test that the middleware handles Bearer token format."""
    # Create mock request with valid Bearer token - values must be properly encoded strings
    mock_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/search",
            "headers": [(b"authorization", b"Bearer test-key-2")],
        }
    )

    # Process request - should pass through without exception
    result = await auth_middleware.process_request(mock_request)
    assert result == mock_request


@pytest.mark.asyncio
async def test_auth_middleware_skip_paths(auth_middleware):
    """Test that the middleware skips authentication for allowed paths."""
    # Create mock request to a skipped path
    mock_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [],  # No API key, but should pass due to path
        }
    )

    # Process request - should pass through without exception
    result = await auth_middleware.process_request(mock_request)
    assert result == mock_request


@pytest.mark.asyncio
async def test_error_to_http_response():
    """Test converting AuthenticationError to HTTP response."""
    # Create authentication error
    error = AuthenticationError(message="Test authentication error")
    
    # Convert to HTTP response
    response = http_error_response(error)
    
    # Verify response structure
    assert response["error_type"] == "AuthenticationError"
    assert response["message"] == "Test authentication error"
    assert response["status_code"] == 401