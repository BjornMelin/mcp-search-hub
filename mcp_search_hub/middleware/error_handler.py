"""Error handling middleware for MCP Search Hub.

This middleware provides centralized error handling for all middleware
components and response formatting for consistent error responses.
"""

import traceback
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..utils.errors import ProviderRateLimitError, SearchError, http_error_response
from ..utils.logging import get_logger

logger = get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware for consistent error handling and formatting."""

    def __init__(self, app, **options):
        """Initialize error handling middleware.

        Args:
            app: ASGI application
            **options: Configuration options including:
                - include_traceback: Whether to include tracebacks in error responses
                - redact_sensitive_data: Whether to redact sensitive data from error responses
        """
        super().__init__(app)
        self.include_traceback = options.get("include_traceback", False)
        self.redact_sensitive_data = options.get("redact_sensitive_data", True)

        logger.info(
            f"Error handler middleware initialized with include_traceback={self.include_traceback}"
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process HTTP requests with error handling.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or handler

        Returns:
            The response from downstream or an error response
        """
        try:
            return await call_next(request)

        except Exception as exc:
            # Log the exception
            logger.error(f"Caught exception in error handler: {exc}", exc_info=True)

            # Convert exception to standardized error response
            error_dict = http_error_response(exc)
            status_code = error_dict.pop("status_code", 500)

            # Add traceback if enabled
            if self.include_traceback:
                error_dict["traceback"] = traceback.format_exc()

            # Check if the error has special header requirements (like rate limit errors)
            headers = {}
            if isinstance(exc, SearchError) and "headers" in exc.details:
                headers = exc.details["headers"]

            # Special handling for rate limit errors
            if isinstance(
                exc, ProviderRateLimitError
            ) and "retry_after_seconds" in error_dict.get("details", {}):
                headers["X-RateLimit-Retry-After"] = str(
                    int(error_dict["details"]["retry_after_seconds"])
                )

            # Log error details
            logger.error(f"Error in request: {error_dict}")

            # Create consistent JSON response
            return JSONResponse(
                status_code=status_code,
                content=error_dict,
                headers=headers,
            )
