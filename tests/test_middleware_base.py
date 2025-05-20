"""Tests for base middleware infrastructure."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import Context
from starlette.requests import Request
from starlette.responses import Response

from mcp_search_hub.middleware.base import BaseMiddleware, MiddlewareManager


class TestMiddleware(BaseMiddleware):
    """Test implementation of BaseMiddleware."""

    def __init__(self, **options):
        """Initialize test middleware."""
        self.request_processed = False
        self.response_processed = False
        self.error_on_request = options.get("error_on_request", False)
        self.error_on_response = options.get("error_on_response", False)
        super().__init__(**options)

    def _initialize(self, **options):
        """Test initialization hook."""
        self.init_called = True
        self.custom_value = options.get("custom_value")

    async def process_request(self, request, context=None):
        """Test request processing."""
        self.request_processed = True
        if self.error_on_request:
            raise ValueError("Test error in request processing")
        return {"processed": True, "original": request}

    async def process_response(self, response, request, context=None):
        """Test response processing."""
        self.response_processed = True
        if self.error_on_response:
            raise ValueError("Test error in response processing")
        return {"processed": True, "original": response}


class TestBaseMiddleware:
    """Test cases for BaseMiddleware."""

    def test_initialization(self):
        """Test middleware initialization."""
        middleware = TestMiddleware(enabled=True, order=50, custom_value="test")

        assert middleware.enabled is True
        assert middleware.order == 50
        assert middleware.init_called is True
        assert middleware.custom_value == "test"
        assert middleware.name == "TestMiddleware"

    @pytest.mark.asyncio
    async def test_call_middleware_success(self):
        """Test successful middleware execution."""
        middleware = TestMiddleware()

        request = {"test": "request"}
        next_handler = AsyncMock(return_value={"test": "response"})

        result = await middleware(request, next_handler)

        assert middleware.request_processed is True
        assert middleware.response_processed is True
        assert next_handler.called is True
        assert next_handler.call_args[0][0] == {
            "processed": True,
            "original": {"test": "request"},
        }
        assert result == {"processed": True, "original": {"test": "response"}}

    @pytest.mark.asyncio
    async def test_call_middleware_disabled(self):
        """Test disabled middleware is bypassed."""
        middleware = TestMiddleware(enabled=False)

        request = {"test": "request"}
        next_handler = AsyncMock(return_value={"test": "response"})

        result = await middleware(request, next_handler)

        assert middleware.request_processed is False
        assert middleware.response_processed is False
        assert next_handler.called is True
        assert next_handler.call_args[0][0] == {"test": "request"}
        assert result == {"test": "response"}

    @pytest.mark.asyncio
    async def test_call_middleware_request_error(self):
        """Test middleware with error in request processing."""
        middleware = TestMiddleware(error_on_request=True)

        request = {"test": "request"}
        next_handler = AsyncMock()

        with pytest.raises(ValueError, match="Test error in request processing"):
            await middleware(request, next_handler)

        assert middleware.request_processed is True
        assert middleware.response_processed is False
        assert next_handler.called is False

    @pytest.mark.asyncio
    async def test_call_middleware_response_error(self):
        """Test middleware with error in response processing."""
        middleware = TestMiddleware(error_on_response=True)

        request = {"test": "request"}
        next_handler = AsyncMock(return_value={"test": "response"})

        with pytest.raises(ValueError, match="Test error in response processing"):
            await middleware(request, next_handler)

        assert middleware.request_processed is True
        assert middleware.response_processed is True
        assert next_handler.called is True


class TestMiddlewareManager:
    """Test cases for MiddlewareManager."""

    def test_add_middleware(self):
        """Test adding middleware to manager."""
        manager = MiddlewareManager()

        manager.add_middleware(TestMiddleware, order=50)
        manager.add_middleware(TestMiddleware, order=20)
        manager.add_middleware(TestMiddleware, order=100)

        assert len(manager.middlewares) == 3
        # Verify ordering
        assert manager.middlewares[0].order == 20
        assert manager.middlewares[1].order == 50
        assert manager.middlewares[2].order == 100

    def test_add_http_middleware(self):
        """Test adding HTTP middleware to manager."""
        manager = MiddlewareManager()

        mock_http_middleware = MagicMock()

        manager.add_http_middleware(mock_http_middleware, option1="value1")
        manager.add_http_middleware(mock_http_middleware, option2="value2")

        assert len(manager.http_middlewares) == 2
        assert manager.http_middlewares[0][0] == mock_http_middleware
        assert manager.http_middlewares[0][1] == {"option1": "value1"}
        assert manager.http_middlewares[1][0] == mock_http_middleware
        assert manager.http_middlewares[1][1] == {"option2": "value2"}

    def test_apply_http_middlewares(self):
        """Test applying HTTP middlewares to an app."""
        manager = MiddlewareManager()

        mock_app = MagicMock()
        mock_middleware1 = MagicMock(return_value="app1")
        mock_middleware2 = MagicMock(return_value="app2")

        manager.add_http_middleware(mock_middleware1, option1="value1")
        manager.add_http_middleware(mock_middleware2, option2="value2")

        result = manager.apply_http_middlewares(mock_app)

        # The last added middleware should be applied first
        mock_middleware2.assert_called_once_with(mock_app, option2="value2")
        mock_middleware1.assert_called_once_with("app2", option1="value1")
        assert result == "app1"

    @pytest.mark.asyncio
    async def test_process_http_request(self):
        """Test processing HTTP request through middleware stack."""
        manager = MiddlewareManager()

        # Add middlewares with different orders to test execution order
        manager.add_middleware(TestMiddleware, order=2, custom_value="first")
        manager.add_middleware(TestMiddleware, order=1, custom_value="second")

        mock_request = MagicMock(spec=Request)
        mock_handler = AsyncMock(return_value=MagicMock(spec=Response))

        await manager.process_http_request(mock_request, mock_handler)

        # Verify handler was called with the processed request
        assert mock_handler.called
        # The processed request should have gone through both middlewares
        assert mock_handler.call_args[0][0]["processed"] is True
        assert mock_handler.call_args[0][0]["original"]["processed"] is True

    @pytest.mark.asyncio
    async def test_process_tool_request(self):
        """Test processing tool request through middleware stack."""
        manager = MiddlewareManager()

        # Add middlewares with different orders to test execution order
        manager.add_middleware(TestMiddleware, order=2, custom_value="first")
        manager.add_middleware(TestMiddleware, order=1, custom_value="second")

        mock_params = {"param1": "value1"}
        mock_context = MagicMock(spec=Context)
        mock_handler = AsyncMock(return_value={"result": "success"})

        result = await manager.process_tool_request(
            mock_params, mock_context, mock_handler
        )

        # Verify handler was called with processed params
        assert mock_handler.called

        # Check the result was processed by both middlewares
        assert result["processed"] is True
        assert result["original"]["processed"] is True
        assert result["original"]["original"]["result"] == "success"

    @pytest.mark.asyncio
    async def test_create_http_middleware(self):
        """Test creating HTTP middleware function."""
        manager = MiddlewareManager()

        # Mock the process_http_request method
        manager.process_http_request = AsyncMock()

        # Create the middleware function
        middleware_func = manager.create_http_middleware()

        # Test calling the middleware function
        mock_request = MagicMock(spec=Request)
        mock_call_next = AsyncMock()

        await middleware_func(mock_request, mock_call_next)

        # Verify process_http_request was called with the correct arguments
        manager.process_http_request.assert_called_once_with(
            mock_request, mock_call_next
        )

    @pytest.mark.asyncio
    async def test_create_tool_middleware(self):
        """Test creating tool middleware function."""
        manager = MiddlewareManager()

        # Mock the process_tool_request method
        manager.process_tool_request = AsyncMock()

        # Create the middleware function
        middleware_func = manager.create_tool_middleware()

        # Test calling the middleware function
        mock_params = {"param1": "value1"}
        mock_context = MagicMock(spec=Context)
        mock_handler = AsyncMock()

        await middleware_func(mock_params, mock_context, mock_handler)

        # Verify process_tool_request was called with the correct arguments
        manager.process_tool_request.assert_called_once_with(
            mock_params, mock_context, mock_handler
        )
