"""Tests for server middleware integration."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import Context
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp_search_hub.middleware.auth import AuthMiddleware
from mcp_search_hub.middleware.base import BaseMiddleware, MiddlewareManager
from mcp_search_hub.middleware.logging import LoggingMiddleware
from mcp_search_hub.middleware.rate_limit import RateLimitMiddleware


class TestMiddlewareSetup:
    """Test to ensure middleware setup works correctly."""

    def test_middleware_manager_with_auth_middleware(self):
        """Test adding auth middleware to manager."""
        manager = MiddlewareManager()

        # Add auth middleware
        manager.add_middleware(
            AuthMiddleware,
            api_keys=["test_key"],
            skip_auth_paths=["/health", "/metrics"],
        )

        # Verify middleware was added
        assert len(manager.middlewares) == 1
        assert isinstance(manager.middlewares[0], AuthMiddleware)

        # Check configuration
        middleware = manager.middlewares[0]
        assert middleware.api_keys == ["test_key"]
        assert "/health" in middleware.skip_auth_paths
        assert "/metrics" in middleware.skip_auth_paths

    def test_middleware_manager_with_rate_limit_middleware(self):
        """Test adding rate limit middleware to manager."""
        manager = MiddlewareManager()

        # Add rate limit middleware
        manager.add_middleware(
            RateLimitMiddleware,
            limit=100,
            window=60,
            global_limit=1000,
            global_window=60,
        )

        # Verify middleware was added
        assert len(manager.middlewares) == 1
        assert isinstance(manager.middlewares[0], RateLimitMiddleware)

        # Check configuration
        middleware = manager.middlewares[0]
        assert middleware.limit == 100
        assert middleware.window == 60
        assert middleware.global_limiter.limit == 1000
        assert middleware.global_limiter.window == 60

    def test_middleware_manager_with_logging_middleware(self):
        """Test adding logging middleware to manager."""
        manager = MiddlewareManager()

        # Add logging middleware
        manager.add_middleware(
            LoggingMiddleware,
            log_level="DEBUG",
            include_headers=True,
            include_body=False,
        )

        # Verify middleware was added
        assert len(manager.middlewares) == 1
        assert isinstance(manager.middlewares[0], LoggingMiddleware)

        # Check configuration
        middleware = manager.middlewares[0]
        assert middleware.log_level == "DEBUG"
        assert middleware.include_headers is True
        assert middleware.include_body is False


class TestHttpMiddlewareWrapper:
    """Test a custom HTTP middleware wrapper similar to the one in server.py."""

    class MiddlewareHTTPWrapper:
        """Simple HTTP middleware wrapper for testing."""

        def __init__(self, app, middleware_manager):
            self.app = app
            self.middleware_manager = middleware_manager

        async def dispatch(self, request, call_next):
            """Process HTTP request through middleware manager."""
            try:
                return await self.middleware_manager.process_http_request(
                    request, call_next
                )
            except Exception as e:
                # If middleware raised an exception with a JSONResponse, return it
                if (
                    hasattr(e, "args")
                    and len(e.args) > 0
                    and isinstance(e.args[0], JSONResponse)
                ):
                    return e.args[0]

                # Otherwise create a generic error response
                error_response = {
                    "error": "ServerError",
                    "message": "An error occurred processing the request",
                    "status_code": 500,
                }
                return JSONResponse(status_code=500, content=error_response)

    @pytest.mark.asyncio
    async def test_middleware_wrapper_dispatch(self):
        """Test the middleware HTTP wrapper dispatch method."""
        # Create a mock middleware manager
        middleware_manager = MagicMock()
        middleware_manager.process_http_request = AsyncMock()

        # Create a wrapper instance
        wrapper = self.MiddlewareHTTPWrapper(MagicMock(), middleware_manager)

        # Create mock request and call_next
        mock_request = MagicMock(spec=Request)
        mock_call_next = AsyncMock()

        # Test normal dispatch
        await wrapper.dispatch(mock_request, mock_call_next)

        # Verify middleware manager was called
        middleware_manager.process_http_request.assert_called_once_with(
            mock_request, mock_call_next
        )

    @pytest.mark.asyncio
    async def test_middleware_wrapper_exception_handling(self):
        """Test exception handling in middleware wrapper."""
        # Create a mock middleware manager that raises an exception
        middleware_manager = MagicMock()
        error_response = JSONResponse(
            status_code=401,
            content={"error": "Unauthorized", "message": "Invalid API key"},
        )
        exception = Exception(error_response)  # Exception with response as arg
        middleware_manager.process_http_request = AsyncMock(side_effect=exception)

        # Create a wrapper instance
        wrapper = self.MiddlewareHTTPWrapper(MagicMock(), middleware_manager)

        # Create mock request and call_next
        mock_request = MagicMock(spec=Request)
        mock_call_next = AsyncMock()

        # Test exception handling with JSONResponse in args
        response = await wrapper.dispatch(mock_request, mock_call_next)

        # Verify the response was extracted from the exception
        assert response == error_response
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_middleware_wrapper_generic_exception(self):
        """Test generic exception handling in middleware wrapper."""
        # Create a mock middleware manager that raises a generic exception
        middleware_manager = MagicMock()
        middleware_manager.process_http_request = AsyncMock(
            side_effect=ValueError("Test error")
        )

        # Create a wrapper instance
        wrapper = self.MiddlewareHTTPWrapper(MagicMock(), middleware_manager)

        # Create mock request and call_next
        mock_request = MagicMock(spec=Request)
        mock_call_next = AsyncMock()

        # Test exception handling with generic exception
        response = await wrapper.dispatch(mock_request, mock_call_next)

        # Verify a 500 error response was created
        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        content = json.loads(response.body.decode("utf-8"))
        assert content["error"] == "ServerError"
        assert "message" in content


class TestToolMiddlewareIntegration:
    """Test integration of middleware with tool execution."""

    @pytest.mark.asyncio
    async def test_tool_middleware_integration(self):
        """Test middleware integration with tool execution."""
        # Create middleware manager
        manager = MiddlewareManager()

        # Add a tracking middleware to verify execution
        tracker = []

        class ToolTrackingMiddleware(BaseMiddleware):
            """Middleware that tracks tool calls."""

            async def process_request(self, request, context=None):
                tracker.append(f"request: {request.get('tool_name')}")
                return request

            async def process_response(self, response, request, context=None):
                tracker.append(f"response: {request.get('tool_name')}")
                return response

        # Add the tracker middleware
        manager.add_middleware(ToolTrackingMiddleware)

        # Create test parameters and context
        params = {
            "query": "test query",
            "max_results": 10,
            "raw_content": False,
            "tool_name": "search",
        }

        mock_context = MagicMock(spec=Context)

        # Create a handler function
        async def handler(**p):
            # Verify params are received correctly
            assert p["query"] == "test query"
            assert p["max_results"] == 10
            assert p["raw_content"] is False
            # tool_name should be there as we need it in middleware
            assert p.get("tool_name") == "search"

            return {"results": ["test result"], "status": "success"}

        # Process through middleware
        result = await manager.process_tool_request(params, mock_context, handler)

        # Verify middleware was executed for this tool
        assert len(tracker) == 2
        assert tracker[0] == "request: search"
        assert tracker[1] == "response: search"

        # Verify result was processed and returned
        assert result["results"] == ["test result"]
        assert result["status"] == "success"


class TestProviderToolsMiddleware:
    """Test middleware integration with provider tools."""

    @pytest.mark.asyncio
    async def test_provider_tool_middleware_integration(self):
        """Test middleware with provider tool parameters."""
        # Create middleware manager
        manager = MiddlewareManager()

        # Add a middleware that verifies provider parameters
        class ProviderMiddleware(BaseMiddleware):
            """Middleware that verifies provider parameters."""

            async def process_request(self, request, context=None):
                # Verify provider information
                if isinstance(request, dict):
                    assert request.get("provider") == "mock_provider"
                    assert request.get("original_tool_name") == "test_tool"
                return request

            async def process_response(self, response, request, context=None):
                # Mark that middleware processed this response
                if isinstance(response, dict):
                    response = response.copy()
                    response["middleware_processed"] = True
                return response

        # Add the provider middleware
        manager.add_middleware(ProviderMiddleware)

        # Create provider tool params with necessary metadata
        params = {
            "param1": "value1",
            "param2": "value2",
            "tool_name": "mock_provider_test_tool",
            "provider": "mock_provider",
            "original_tool_name": "test_tool",
        }

        mock_context = MagicMock(spec=Context)

        # Mock handler for provider tool
        async def handler(**p):
            # Provider-specific params should be available
            assert p["param1"] == "value1"
            assert p["param2"] == "value2"
            # Tool info should be available too
            assert p["tool_name"] == "mock_provider_test_tool"
            assert p["provider"] == "mock_provider"
            assert p["original_tool_name"] == "test_tool"

            return {"provider_result": "success"}

        # Process through middleware
        result = await manager.process_tool_request(params, mock_context, handler)

        # Verify middleware processed result
        assert result["middleware_processed"] is True
        assert result["provider_result"] == "success"


class TestMiddlewareIntegrationPatterns:
    """Test how middleware integrates with different patterns."""

    @pytest.mark.asyncio
    async def test_http_middleware_integration(self):
        """Test middleware integration with HTTP requests."""
        # Create middleware manager
        manager = MiddlewareManager()

        # Add middleware that adds headers to responses
        class HeaderMiddleware(BaseMiddleware):
            """Middleware that adds headers to responses."""

            async def process_request(self, request, context=None):
                if isinstance(request, Request):
                    # Check that this is the right route
                    assert request.url.path == "/health"
                return request

            async def process_response(self, response, request, context=None):
                if isinstance(response, Response):
                    # Add a custom header to outgoing response
                    response.headers["X-Processed-By"] = "HeaderMiddleware"
                return response

        # Add our middleware
        manager.add_middleware(HeaderMiddleware)

        # Create mock request and response
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/health"

        mock_response = MagicMock(spec=Response)
        mock_response.headers = {}

        # Create handler that returns the response
        async def handle_request(req):
            return mock_response

        # Process through middleware
        result = await manager.process_http_request(mock_request, handle_request)

        # Verify middleware added headers
        assert result == mock_response
        assert result.headers["X-Processed-By"] == "HeaderMiddleware"

    @pytest.mark.asyncio
    async def test_multiple_middleware_chain(self):
        """Test chaining multiple middleware components."""
        manager = MiddlewareManager()

        # Add middleware that captures stages
        execution_order = []

        class FirstMiddleware(BaseMiddleware):
            """First middleware in chain."""

            def _initialize(self, **options):
                self.order = 1

            async def process_request(self, request, context=None):
                execution_order.append("first_request")
                return request

            async def process_response(self, response, request, context=None):
                execution_order.append("first_response")
                return response

        class SecondMiddleware(BaseMiddleware):
            """Second middleware in chain."""

            def _initialize(self, **options):
                self.order = 2

            async def process_request(self, request, context=None):
                execution_order.append("second_request")
                return request

            async def process_response(self, response, request, context=None):
                execution_order.append("second_response")
                return response

        # Add both middlewares
        manager.add_middleware(SecondMiddleware)  # Add out of order
        manager.add_middleware(FirstMiddleware)

        # Create mock request and handler
        mock_request = MagicMock(spec=Request)

        async def handle_request(req):
            execution_order.append("handler")
            return "response"

        # Process through middleware pipeline
        await manager.process_http_request(mock_request, handle_request)

        # Verify execution order follows middleware pipeline pattern:
        # first_request → second_request → handler → second_response → first_response
        assert execution_order == [
            "first_request",
            "second_request",
            "handler",
            "second_response",
            "first_response",
        ]
