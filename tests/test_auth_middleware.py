"""Tests for authentication middleware."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Context
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_search_hub.middleware.auth import AuthMiddleware


class TestAuthMiddleware:
    """Test cases for AuthMiddleware."""

    def test_initialization_with_api_keys(self):
        """Test initialization with explicit API keys."""
        middleware = AuthMiddleware(
            api_keys=["test_key1", "test_key2"], skip_auth_paths=["/skip1", "/skip2"]
        )

        assert middleware.api_keys == ["test_key1", "test_key2"]
        assert middleware.skip_auth_paths == ["/skip1", "/skip2"]
        assert middleware.order == 10  # Default auth order

    def test_initialization_with_env_var(self):
        """Test initialization with API key from environment."""
        with patch.dict(os.environ, {"MCP_SEARCH_HUB_API_KEY": "env_key"}):
            middleware = AuthMiddleware()

            assert middleware.api_keys == ["env_key"]
            assert middleware.skip_auth_paths == [
                "/health",
                "/metrics",
                "/docs",
                "/redoc",
                "/openapi.json",
            ]

    def test_initialization_without_api_keys(self):
        """Test initialization without API keys."""
        with patch.dict(os.environ, clear=True):
            middleware = AuthMiddleware()

            assert middleware.api_keys == []

    @pytest.mark.asyncio
    async def test_process_request_no_api_keys(self):
        """Test processing request when no API keys are configured."""
        middleware = AuthMiddleware(api_keys=[])

        # Test with HTTP request
        mock_request = MagicMock(spec=Request)
        result = await middleware.process_request(mock_request)
        assert result == mock_request

        # Test with tool request
        mock_tool_request = {"param": "value"}
        result = await middleware.process_request(mock_tool_request)
        assert result == mock_tool_request

    @pytest.mark.asyncio
    async def test_process_tool_request(self):
        """Test processing tool request (should always pass through)."""
        middleware = AuthMiddleware(api_keys=["test_key"])

        mock_tool_request = {"param": "value"}
        mock_context = MagicMock(spec=Context)

        result = await middleware.process_request(mock_tool_request, mock_context)
        assert result == mock_tool_request

    @pytest.mark.asyncio
    async def test_process_http_request_skipped_path(self):
        """Test processing HTTP request for path that skips authentication."""
        middleware = AuthMiddleware(
            api_keys=["test_key"], skip_auth_paths=["/health", "/docs"]
        )

        # Create mock request with skipped path
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/health"

        result = await middleware.process_request(mock_request)
        assert result == mock_request

    @pytest.mark.asyncio
    async def test_process_http_request_valid_key_header(self):
        """Test processing HTTP request with valid API key in X-API-Key header."""
        middleware = AuthMiddleware(api_keys=["test_key"])

        # Create mock request with valid API key
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/search"
        mock_request.headers = {"X-API-Key": "test_key"}

        result = await middleware.process_request(mock_request)
        assert result == mock_request

    @pytest.mark.asyncio
    async def test_process_http_request_valid_key_bearer(self):
        """Test processing HTTP request with valid API key in Authorization header."""
        middleware = AuthMiddleware(api_keys=["test_key"])

        # Create mock request with valid bearer token
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/search"
        mock_request.headers = {"Authorization": "Bearer test_key"}

        result = await middleware.process_request(mock_request)
        assert result == mock_request

    @pytest.mark.asyncio
    async def test_process_http_request_invalid_key(self):
        """Test processing HTTP request with invalid API key."""
        middleware = AuthMiddleware(api_keys=["test_key"])

        # Create mock request with invalid API key
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/search"
        mock_request.headers = {"X-API-Key": "invalid_key"}

        # Should raise AuthenticationError
        from mcp_search_hub.utils.errors import AuthenticationError
        
        with pytest.raises(AuthenticationError) as exc_info:
            await middleware.process_request(mock_request)

        # Check the error details
        error = exc_info.value
        assert error.message == "Invalid or missing API key"
        assert error.status_code == 401

    @pytest.mark.asyncio
    async def test_process_http_request_missing_key(self):
        """Test processing HTTP request with missing API key."""
        middleware = AuthMiddleware(api_keys=["test_key"])

        # Create mock request without API key
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/search"
        mock_request.headers = {}

        # Should raise AuthenticationError
        from mcp_search_hub.utils.errors import AuthenticationError
        
        with pytest.raises(AuthenticationError) as exc_info:
            await middleware.process_request(mock_request)

        # Check the error details
        error = exc_info.value
        assert error.message == "Invalid or missing API key"
        assert error.status_code == 401

    @pytest.mark.asyncio
    async def test_process_response(self):
        """Test processing response (should be unchanged)."""
        middleware = AuthMiddleware()

        mock_response = {"result": "success"}
        mock_request = MagicMock(spec=Request)

        result = await middleware.process_response(mock_response, mock_request)
        assert result == mock_response


@pytest.mark.parametrize(
    "api_keys,header_key,header_value,path,should_pass",
    [
        # No API keys configured - should always pass
        ([], None, None, "/search", True),
        # Valid API key in X-API-Key header
        (["key1", "key2"], "X-API-Key", "key1", "/search", True),
        # Valid API key in Authorization header (Bearer)
        (["key1", "key2"], "Authorization", "Bearer key2", "/search", True),
        # Invalid API key
        (["key1", "key2"], "X-API-Key", "invalid", "/search", False),
        # Missing API key
        (["key1", "key2"], None, None, "/search", False),
        # Skipped path - should pass regardless of API key
        (["key1", "key2"], None, None, "/health", True),
        (["key1", "key2"], None, None, "/metrics", True),
        (["key1", "key2"], None, None, "/docs", True),
    ],
)
@pytest.mark.asyncio
async def test_auth_middleware_scenarios(
    api_keys, header_key, header_value, path, should_pass
):
    """Test various authentication scenarios."""
    middleware = AuthMiddleware(api_keys=api_keys)

    # Create mock request
    mock_request = MagicMock(spec=Request)
    mock_request.url.path = path
    mock_request.headers = {}

    if header_key and header_value:
        mock_request.headers[header_key] = header_value

    if should_pass:
        # Should pass authentication
        result = await middleware.process_request(mock_request)
        assert result == mock_request
    else:
        # Should fail authentication
        from mcp_search_hub.utils.errors import AuthenticationError
        
        with pytest.raises(AuthenticationError) as exc_info:
            await middleware.process_request(mock_request)

        error = exc_info.value
        assert error.message == "Invalid or missing API key"
        assert error.status_code == 401
