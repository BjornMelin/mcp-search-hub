"""Base middleware infrastructure for MCP Search Hub.

This module provides the foundation for implementing middleware patterns
in the MCP Search Hub. It allows for pre-processing requests and post-processing
responses with a clean, reusable interface.
"""

import abc
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastmcp import Context
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..utils.logging import get_logger

# Type definitions
T = TypeVar("T")
MiddlewareFunction = Callable[[Any, Callable[..., Awaitable[T]]], Awaitable[T]]
HTTPMiddlewareFunction = Callable[
    [Request, Callable[..., Awaitable[Response]]], Awaitable[Response]
]
ToolMiddlewareFunction = Callable[
    [dict, Context, Callable[..., Awaitable[Any]]], Awaitable[Any]
]

logger = get_logger(__name__)


class BaseMiddleware(abc.ABC):
    """Base class for middleware components.

    This abstract class defines the interface for all middleware components
    in the MCP Search Hub. Each middleware must implement the process_request
    and/or process_response methods.
    """

    def __init__(self, **options):
        """Initialize the middleware.

        Args:
            **options: Configuration options for the middleware
        """
        self.options = options
        self.enabled = options.get("enabled", True)
        self.order = options.get("order", 100)
        self.logger = get_logger(self.__class__.__module__)
        self.name = self.__class__.__name__
        self._initialize(**options)

    def _initialize(self, **options):
        """Additional initialization that subclasses can override."""

    @abc.abstractmethod
    async def process_request(
        self, request: Any, context: Context | None = None
    ) -> Any:
        """Process the incoming request.

        Args:
            request: The incoming request (can be HTTP Request or tool parameters)
            context: Optional Context object for tool requests

        Returns:
            Modified request or original request if no modifications

        Raises:
            Exception: If the request should be rejected
        """
        return request

    @abc.abstractmethod
    async def process_response(
        self, response: Any, request: Any, context: Context | None = None
    ) -> Any:
        """Process the outgoing response.

        Args:
            response: The response to be returned
            request: The original request
            context: Optional Context object for tool requests

        Returns:
            Modified response or original response if no modifications
        """
        return response

    async def __call__(
        self,
        request: Any,
        call_next: Callable[..., Awaitable[Any]],
        context: Context | None = None,
    ) -> Any:
        """Execute the middleware.

        Args:
            request: The incoming request
            call_next: The next middleware or handler function
            context: Optional Context object

        Returns:
            The response from downstream
        """
        if not self.enabled:
            return await call_next(request)

        try:
            # Process request (pre-processing)
            modified_request = await self.process_request(request, context)

            # Call the next middleware/handler
            response = await call_next(modified_request)

            # Process response (post-processing)
            return await self.process_response(response, request, context)
        except Exception as e:
            self.logger.error(f"Error in middleware {self.name}: {str(e)}")
            raise  # Re-raise for error handling middleware to catch


class MiddlewareManager:
    """Manages the middleware pipeline for MCP Search Hub.

    This class handles the registration, ordering, and execution of middleware
    components across both HTTP and tool contexts.
    """

    def __init__(self):
        """Initialize the middleware manager."""
        self.middlewares: list[BaseMiddleware] = []
        self.http_middlewares: list[BaseHTTPMiddleware] = []
        self._initialized = False

    def add_middleware(self, middleware_class: type[BaseMiddleware], **options):
        """Add a middleware to the middleware stack.

        Args:
            middleware_class: Middleware class to instantiate
            **options: Options to pass to the middleware constructor
        """
        middleware = middleware_class(**options)
        self.middlewares.append(middleware)
        # Re-sort middleware by order
        self.middlewares.sort(key=lambda m: m.order)

    def add_http_middleware(
        self, middleware_class: type[BaseHTTPMiddleware], **options
    ):
        """Add a Starlette HTTP middleware to the stack.

        Args:
            middleware_class: HTTP middleware class
            **options: Options to pass to the middleware constructor
        """
        self.http_middlewares.append((middleware_class, options))

    def apply_http_middlewares(self, app):
        """Apply all HTTP middlewares to a Starlette/FastAPI app.

        Args:
            app: The app to apply middlewares to

        Returns:
            App with middlewares applied
        """
        # Apply in reverse order so that first added = outermost middleware
        for middleware_class, options in reversed(self.http_middlewares):
            app = middleware_class(app, **options)
        return app

    async def process_http_request(self, request: Request, call_next) -> Response:
        """Process an HTTP request through the middleware stack.

        Args:
            request: The incoming HTTP request
            call_next: The next handler in the chain

        Returns:
            The HTTP response
        """
        # Create a pipeline of our middleware
        middleware_chain = deque(self.middlewares)

        async def process_middleware(
            req: Request, mw_chain: deque[BaseMiddleware]
        ) -> Response:
            if not mw_chain:
                # No more middleware, call the final handler
                return await call_next(req)

            # Get the next middleware
            middleware = mw_chain.popleft()

            # Execute it and continue the chain
            return await middleware(req, lambda r: process_middleware(r, mw_chain))

        # Start the middleware chain
        return await process_middleware(request, middleware_chain)

    async def process_tool_request(
        self, params: dict, context: Context, handler: Callable[..., Awaitable[Any]]
    ) -> Any:
        """Process a tool request through the middleware stack.

        Args:
            params: The tool parameters
            context: The tool execution context
            handler: The tool handler function

        Returns:
            The tool response
        """
        # Create a pipeline of our middleware
        middleware_chain = deque(self.middlewares)

        async def process_middleware(
            p: dict, ctx: Context, mw_chain: deque[BaseMiddleware]
        ) -> Any:
            if not mw_chain:
                # No more middleware, call the final handler
                return await handler(**p)

            # Get the next middleware
            middleware = mw_chain.popleft()

            # Execute it and continue the chain
            return await middleware(
                p,
                lambda modified_params: process_middleware(
                    modified_params, ctx, mw_chain
                ),
                ctx,
            )

        # Start the middleware chain
        return await process_middleware(params, context, middleware_chain)

    def create_http_middleware(self) -> HTTPMiddlewareFunction:
        """Create a Starlette middleware function for HTTP requests.

        Returns:
            A middleware function for Starlette
        """

        async def middleware(request: Request, call_next):
            return await self.process_http_request(request, call_next)

        return middleware

    def create_tool_middleware(self) -> ToolMiddlewareFunction:
        """Create a middleware function for tool execution.

        Returns:
            A middleware function for tool execution
        """

        async def middleware(params: dict, context: Context, handler):
            return await self.process_tool_request(params, context, handler)

        return middleware
