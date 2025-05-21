"""Error handling middleware for MCP Search Hub.

This middleware provides centralized error handling for all middleware
components and response formatting for consistent error responses.
"""

from typing import Any

from fastmcp import Context
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..utils.errors import SearchError, http_error_response
from ..utils.logging import get_logger
from .base import BaseMiddleware

logger = get_logger(__name__)


class ErrorHandlerMiddleware(BaseMiddleware):
    """Middleware for consistent error handling and formatting."""

    def _initialize(self, **options):
        """Initialize error handling middleware.

        Args:
            **options: Configuration options including:
                - include_traceback: Whether to include tracebacks in error responses
                - order: Middleware execution order (default: 0)
        """
        # Error handler should be first in the chain (last to process response)
        # This ensures it can catch errors from all other middleware
        self.order = options.get("order", 0)
        self.include_traceback = options.get("include_traceback", False)

        logger.info(
            f"Error handler middleware initialized with include_traceback={self.include_traceback}"
        )

    async def process_request(
        self, request: Any, context: Context | None = None
    ) -> Any:
        """Process the incoming request (no modifications).

        Args:
            request: The incoming request (HTTP or tool params)
            context: Optional Context object for tool requests

        Returns:
            The unmodified request
        """
        # No pre-processing needed for error handler
        return request

    async def process_response(
        self, response: Any, request: Any, context: Context | None = None
    ) -> Any:
        """Process the outgoing response for consistent error formatting.

        Args:
            response: The response
            request: The original request
            context: Optional Context object

        Returns:
            The response, possibly converted to a standardized error response
        """
        # If the response is already a valid Response object, no need to modify it
        if not isinstance(response, Exception):
            return response

        # Handle special case where another middleware has returned a Response
        # directly in an exception (used by some middleware for early returns)
        if isinstance(response, JSONResponse):
            return response

        # Convert exception to standardized error response
        if isinstance(request, Request):
            # For HTTP requests, create a JSON Response with appropriate headers
            error_dict = http_error_response(response)
            status_code = error_dict.pop("status_code", 500)

            # Check if the error has special header requirements (like rate limit errors)
            headers = {}
            if isinstance(response, SearchError) and "headers" in response.details:
                headers = response.details["headers"]

            # Log error details
            logger.error(f"Error in request: {error_dict}")

            # Create consistent JSON response
            return JSONResponse(
                status_code=status_code,
                content=error_dict,
                headers=headers,
            )

        # For tool requests, return error in a format FastMCP can handle
        # This will typically be converted to a proper error by FastMCP
        if isinstance(response, SearchError):
            return response.to_dict()
        return {"error": str(response), "type": type(response).__name__}

    async def __call__(
        self,
        request: Any,
        call_next: callable,
        context: Context | None = None,
    ) -> Any:
        """Execute the middleware with error handling.

        This overrides the base implementation to catch exceptions.

        Args:
            request: The incoming request
            call_next: The next middleware or handler function
            context: Optional Context object

        Returns:
            The response from downstream or an error response
        """
        if not self.enabled:
            return await call_next(request)

        try:
            # Process request (no changes for error handler)
            modified_request = await self.process_request(request, context)

            # Call the next middleware/handler
            response = await call_next(modified_request)

            # Process response (convert errors to standard format)
            return await self.process_response(response, request, context)

        except Exception as exc:
            # Log the exception
            logger.error(f"Caught exception in error handler: {exc}", exc_info=True)

            # Convert exception to standardized response
            return await self.process_response(exc, request, context)
