"""Tests for middleware manager ordering and pipeline execution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Context
from starlette.requests import Request
from starlette.responses import Response

from mcp_search_hub.middleware.base import BaseMiddleware, MiddlewareManager


class OrderTrackerMiddleware(BaseMiddleware):
    """Test middleware that tracks execution order."""

    def _initialize(self, **options):
        """Initialize with a tracker list."""
        self.name = options.get("name", "unnamed")
        self.tracker = options.get("tracker", [])

    async def process_request(self, request, context=None):
        """Track request processing order."""
        self.tracker.append(f"{self.name}_request")
        return request

    async def process_response(self, response, request, context=None):
        """Track response processing order."""
        self.tracker.append(f"{self.name}_response")
        return response


class ModifyingMiddleware(BaseMiddleware):
    """Test middleware that modifies request and response."""

    def _initialize(self, **options):
        """Initialize with a name."""
        self.middleware_name = options.get("name", "unnamed")

    async def process_request(self, request, context=None):
        """Modify the request."""
        if isinstance(request, dict):
            request = request.copy()
            request["modified_by"] = self.middleware_name
            request["middleware_chain"] = request.get("middleware_chain", []) + [
                f"{self.middleware_name}_request"
            ]
        return request

    async def process_response(self, response, request, context=None):
        """Modify the response."""
        if isinstance(response, dict):
            response = response.copy()
            response["modified_by"] = self.middleware_name
            response["middleware_chain"] = response.get("middleware_chain", []) + [
                f"{self.middleware_name}_response"
            ]
        return response


class ErroringMiddleware(BaseMiddleware):
    """Test middleware that raises errors."""

    def __init__(self, **options):
        """Initialize with error configuration."""
        self.error_on_request = options.get("error_on_request", False)
        self.error_on_response = options.get("error_on_response", False)
        self.error_message = options.get("error_message", "Test error")
        super().__init__(**options)

    async def process_request(self, request, context=None):
        """Potentially raise error during request processing."""
        if self.error_on_request:
            raise ValueError(f"{self.error_message} in request")
        return request

    async def process_response(self, response, request, context=None):
        """Potentially raise error during response processing."""
        if self.error_on_response:
            raise ValueError(f"{self.error_message} in response")
        return response


class TestMiddlewareOrderingAndExecution:
    """Test case for middleware ordering and execution."""

    @pytest.mark.asyncio
    async def test_middleware_execution_order(self):
        """Test that middlewares execute in correct order based on order value."""
        manager = MiddlewareManager()

        # Create a tracker to record execution order
        tracker = []

        # Add middlewares with different order values
        manager.add_middleware(
            OrderTrackerMiddleware, name="first", order=1, tracker=tracker
        )
        manager.add_middleware(
            OrderTrackerMiddleware, name="third", order=3, tracker=tracker
        )
        manager.add_middleware(
            OrderTrackerMiddleware, name="second", order=2, tracker=tracker
        )

        # Mock request and handler
        mock_request = {"test": "request"}
        mock_handler = AsyncMock(return_value={"test": "response"})

        # Process request through the middleware stack
        await manager.process_tool_request(mock_request, None, mock_handler)

        # Verify execution order:
        # Request phase: first → second → third → handler
        # Response phase: third → second → first
        expected_order = [
            "first_request",  # First middleware processes request
            "second_request",  # Second middleware processes request
            "third_request",  # Third middleware processes request
            "third_response",  # Third middleware processes response
            "second_response",  # Second middleware processes response
            "first_response",  # First middleware processes response
        ]

        assert tracker == expected_order

    @pytest.mark.asyncio
    async def test_middleware_modification_chain(self):
        """Test that middlewares can modify request/response and changes are visible to next middleware."""
        manager = MiddlewareManager()

        # Add middlewares that modify requests/responses
        manager.add_middleware(ModifyingMiddleware, name="first", order=1)
        manager.add_middleware(ModifyingMiddleware, name="second", order=2)
        manager.add_middleware(ModifyingMiddleware, name="third", order=3)

        # Create initial request and mock handler that returns a response with middleware_chain
        initial_request = {"original": "request"}

        async def handler(**params):
            # Handler should see modifications from all middlewares
            assert params["middleware_chain"] == [
                "first_request",
                "second_request",
                "third_request",
            ]
            # Return a response that will be processed by middleware
            return {"original": "response", "middleware_chain": []}

        # Process request through the middleware stack
        result = await manager.process_tool_request(initial_request, None, handler)

        # Verify request was modified by all middlewares
        assert "modified_by" in result
        assert result["modified_by"] == "first"  # Last middleware to touch the response

        # Verify response chain shows correct reverse order
        assert result["middleware_chain"] == [
            "third_response",
            "second_response",
            "first_response",
        ]

    @pytest.mark.asyncio
    async def test_error_handling_in_request_phase(self):
        """Test error handling when a middleware raises error during request phase."""
        manager = MiddlewareManager()

        # Add middlewares including one that errors during request
        manager.add_middleware(OrderTrackerMiddleware, name="first", order=1)
        manager.add_middleware(
            ErroringMiddleware, name="error", order=2, error_on_request=True
        )
        manager.add_middleware(OrderTrackerMiddleware, name="third", order=3)

        # Create request and handler
        mock_request = {"test": "request"}
        mock_handler = AsyncMock()

        # Process request - should raise error
        with pytest.raises(ValueError, match="Test error in request"):
            await manager.process_tool_request(mock_request, None, mock_handler)

        # Verify handler was not called
        assert not mock_handler.called

    @pytest.mark.asyncio
    async def test_error_handling_in_response_phase(self):
        """Test error handling when a middleware raises error during response phase."""
        manager = MiddlewareManager()

        # Create tracker to monitor execution
        tracker = []

        # Add middlewares including one that errors during response
        manager.add_middleware(
            OrderTrackerMiddleware, name="first", order=1, tracker=tracker
        )
        manager.add_middleware(
            ErroringMiddleware, name="error", order=2, error_on_response=True
        )
        manager.add_middleware(
            OrderTrackerMiddleware, name="third", order=3, tracker=tracker
        )

        # Create request and handler
        mock_request = {"test": "request"}
        mock_handler = AsyncMock(return_value={"test": "response"})

        # Process request - should raise error
        with pytest.raises(ValueError, match="Test error in response"):
            await manager.process_tool_request(mock_request, None, mock_handler)

        # Verify all request processing happened and some response processing
        assert "first_request" in tracker
        assert "third_request" in tracker
        assert "third_response" in tracker
        # But first_response should not be there as error occurred before that
        assert "first_response" not in tracker

    @pytest.mark.asyncio
    async def test_disabled_middleware_skipped(self):
        """Test that disabled middlewares are skipped."""
        manager = MiddlewareManager()

        # Create tracker
        tracker = []

        # Add middlewares with middle one disabled
        manager.add_middleware(
            OrderTrackerMiddleware, name="first", order=1, tracker=tracker
        )
        manager.add_middleware(
            OrderTrackerMiddleware,
            name="second",
            order=2,
            enabled=False,
            tracker=tracker,
        )
        manager.add_middleware(
            OrderTrackerMiddleware, name="third", order=3, tracker=tracker
        )

        # Create request and handler
        mock_request = {"test": "request"}
        mock_handler = AsyncMock(return_value={"test": "response"})

        # Process request
        await manager.process_tool_request(mock_request, None, mock_handler)

        # Verify disabled middleware was skipped
        expected_order = [
            "first_request",
            "third_request",
            "third_response",
            "first_response",
        ]
        assert "second_request" not in tracker
        assert "second_response" not in tracker
        assert tracker == expected_order

    @pytest.mark.asyncio
    async def test_http_request_processing(self):
        """Test processing HTTP requests through middleware stack."""
        manager = MiddlewareManager()

        # Create tracker
        tracker = []

        # Add middlewares
        manager.add_middleware(
            OrderTrackerMiddleware, name="first", order=1, tracker=tracker
        )
        manager.add_middleware(
            OrderTrackerMiddleware, name="second", order=2, tracker=tracker
        )

        # Create mock request and response
        mock_request = MagicMock(spec=Request)
        mock_response = MagicMock(spec=Response)
        mock_handler = AsyncMock(return_value=mock_response)

        # Process request
        await manager.process_http_request(mock_request, mock_handler)

        # Verify order
        expected_order = [
            "first_request",
            "second_request",
            "second_response",
            "first_response",
        ]
        assert tracker == expected_order

    @pytest.mark.asyncio
    async def test_complex_middleware_pipeline(self):
        """Test a complex middleware pipeline with HTTP middleware and tool middleware."""
        manager = MiddlewareManager()

        # HTTP middleware
        middleware_func = manager.create_http_middleware()

        # Mock app and request
        mock_app = MagicMock()
        mock_app.side_effect = AsyncMock(return_value="response")
        mock_request = MagicMock(spec=Request)

        # Patch the process_http_request method
        with patch.object(
            manager,
            "process_http_request",
            AsyncMock(return_value="processed_response"),
        ) as mock_process:
            # Call the middleware function
            result = await middleware_func(mock_request, mock_app)

            # Verify process_http_request was called
            mock_process.assert_called_once_with(mock_request, mock_app)
            assert result == "processed_response"

    @pytest.mark.asyncio
    async def test_tool_middleware_creation(self):
        """Test creation and execution of tool middleware."""
        manager = MiddlewareManager()

        # Create tool middleware function
        middleware_func = manager.create_tool_middleware()

        # Mock params, context and handler
        mock_params = {"param": "value"}
        mock_context = MagicMock(spec=Context)
        mock_handler = AsyncMock(return_value="tool_result")

        # Patch the process_tool_request method
        with patch.object(
            manager,
            "process_tool_request",
            AsyncMock(return_value="processed_tool_result"),
        ) as mock_process:
            # Call the middleware function
            result = await middleware_func(mock_params, mock_context, mock_handler)

            # Verify process_tool_request was called
            mock_process.assert_called_once_with(
                mock_params, mock_context, mock_handler
            )
            assert result == "processed_tool_result"


@pytest.mark.asyncio
async def test_middleware_execution_with_context():
    """Test middleware execution with context object."""
    manager = MiddlewareManager()

    # Create a context object with state
    mock_context = MagicMock(spec=Context)
    mock_context.state = {}

    # Create a middleware that accesses context
    class ContextAccessingMiddleware(BaseMiddleware):
        async def process_request(self, request, context=None):
            assert context is not None
            # Store something in context
            context.state["middleware_visited"] = True
            return request

        async def process_response(self, response, request, context=None):
            assert context is not None
            assert context.state["middleware_visited"] is True
            # Add something to the response
            if isinstance(response, dict):
                response = response.copy()
                response["context_accessed"] = True
            return response

    # Add the middleware
    manager.add_middleware(ContextAccessingMiddleware)

    # Mock handler that also accesses context
    async def handler(**params):
        assert mock_context.state["middleware_visited"] is True
        # Add something else to state
        mock_context.state["handler_visited"] = True
        return {"result": "success"}

    # Process request
    result = await manager.process_tool_request(
        {"param": "value"}, mock_context, handler
    )

    # Verify context was accessed
    assert result["context_accessed"] is True
    assert mock_context.state["middleware_visited"] is True
    assert mock_context.state["handler_visited"] is True
