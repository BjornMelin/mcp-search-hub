"""Retry middleware for HTTP requests and tool invocations.

This middleware adds exponential backoff retry logic to HTTP requests and tool
invocations when certain types of transient failures occur.
"""

import asyncio
import random
from typing import Any

import httpx
from fastmcp import Context
from starlette.requests import Request

from ..utils.errors import ProviderTimeoutError, SearchError
from ..utils.logging import get_logger
from .base import BaseMiddleware

logger = get_logger(__name__)

# Retryable HTTP status codes
RETRYABLE_STATUS_CODES: set[int] = {
    408,  # Request Timeout
    429,  # Too Many Requests
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}

# Retryable exception types
RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    ConnectionError,
    TimeoutError,
    ProviderTimeoutError,
)


class RetryMiddleware(BaseMiddleware):
    """Middleware for applying exponential backoff retry logic."""

    def _initialize(self, **options):
        """Initialize retry middleware.

        Args:
            **options: Configuration options including:
                - max_retries: Maximum number of retry attempts
                - base_delay: Initial delay between retries in seconds
                - max_delay: Maximum delay between retries in seconds
                - exponential_base: Base for exponential backoff calculation
                - jitter: Whether to add randomization to delays
                - order: Middleware execution order (default: 30)
        """
        self.order = options.get("order", 30)  # Run after auth and rate limit
        self.max_retries = options.get("max_retries", 3)
        self.base_delay = options.get("base_delay", 1.0)
        self.max_delay = options.get("max_delay", 60.0)
        self.exponential_base = options.get("exponential_base", 2.0)
        self.jitter = options.get("jitter", True)
        self.skip_paths = options.get("skip_paths", ["/health", "/metrics"])

        logger.info(
            f"Retry middleware initialized with max_retries={self.max_retries}, "
            f"base_delay={self.base_delay}s, max_delay={self.max_delay}s"
        )

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a retry attempt using exponential backoff.

        Args:
            attempt: Current retry attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff calculation
        delay = min(self.base_delay * (self.exponential_base**attempt), self.max_delay)

        if self.jitter:
            # Add ±25% jitter to avoid thundering herd problems
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)  # Ensure non-negative

    def is_retryable_exception(self, exc: Exception) -> bool:
        """Check if an exception is retryable.

        Args:
            exc: Exception to check

        Returns:
            True if exception is retryable, False otherwise
        """
        # Check if it's a known retryable exception type
        if isinstance(exc, RETRYABLE_EXCEPTIONS):
            return True

        # Check if it's an HTTP status code exception
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in RETRYABLE_STATUS_CODES

        # Check if it's a search error that might be retryable
        if isinstance(exc, SearchError):
            # Only retry if it's a temporary error
            return "temporary" in str(exc).lower() or "timeout" in str(exc).lower()

        return False

    def should_retry_request(self, request: Any) -> bool:
        """Determine if a request should be retried.

        Args:
            request: The request to check

        Returns:
            True if the request should be handled by retry logic
        """
        # For HTTP requests, check if path is in skip list
        if isinstance(request, Request):
            path = request.url.path
            return path not in self.skip_paths

        # For tool requests, always apply retry logic
        return True

    async def process_request(
        self, request: Any, context: Context | None = None
    ) -> Any:
        """Process the incoming request (pre-processing).

        For retry middleware, we don't modify the request, just pass it through.

        Args:
            request: The incoming request
            context: Optional Context object for tool requests

        Returns:
            Unmodified request
        """
        # No pre-processing needed, just attach retry state for later use
        if isinstance(request, Request):
            request.state.retry_attempt = 0
            request.state.retryable_request = self.should_retry_request(request)

        elif isinstance(request, dict):
            # For tool parameters, add retry state
            request = request.copy()
            request["_retry_attempt"] = 0
            request["_retryable_request"] = self.should_retry_request(request)

        return request

    async def process_response(
        self, response: Any, request: Any, context: Context | None = None
    ) -> Any:
        """Process the outgoing response (post-processing).

        For retry middleware, we don't modify successful responses.

        Args:
            response: The response
            request: The original request
            context: Optional Context object

        Returns:
            Response (either original or from retry)
        """
        # Response was successful, just return it
        return response

    async def __call__(
        self,
        request: Any,
        call_next: callable,
        context: Context | None = None,
    ) -> Any:
        """Execute the middleware with retry logic.

        This overrides the base implementation to implement retry logic.

        Args:
            request: The incoming request
            call_next: The next middleware or handler function
            context: Optional Context object

        Returns:
            The response from downstream
        """
        if not self.enabled:
            return await call_next(request)

        # Process request (add retry state)
        modified_request = await self.process_request(request, context)

        # Check if we should apply retry logic to this request
        retryable_request = False
        if isinstance(modified_request, Request):
            retryable_request = getattr(
                modified_request.state, "retryable_request", False
            )
        elif isinstance(modified_request, dict):
            retryable_request = modified_request.get("_retryable_request", False)

        if not retryable_request:
            # Skip retry logic for excluded paths
            return await call_next(modified_request)

        # Initialize retry state
        attempt = 0
        last_exception = None

        # Retry loop
        while attempt <= self.max_retries:
            try:
                # Update retry counter in request
                if isinstance(modified_request, Request):
                    modified_request.state.retry_attempt = attempt
                elif isinstance(modified_request, dict):
                    modified_request = modified_request.copy()
                    modified_request["_retry_attempt"] = attempt

                # Call the next middleware/handler
                response = await call_next(modified_request)

                # Process response (no changes needed for success)
                return await self.process_response(response, request, context)

            except Exception as exc:
                last_exception = exc

                # Check if this is the last attempt
                if attempt >= self.max_retries:
                    logger.error(
                        f"All retry attempts exhausted ({attempt}/{self.max_retries}): {exc}"
                    )
                    raise

                # Check if the exception is retryable
                if not self.is_retryable_exception(exc):
                    logger.debug(f"Non-retryable exception: {exc}")
                    raise

                # Calculate delay for next attempt
                delay = self.calculate_delay(attempt)

                # Get request info for logging
                request_info = "unknown"
                if isinstance(request, Request):
                    request_info = f"{request.method} {request.url.path}"
                elif isinstance(request, dict) and "tool_name" in request:
                    request_info = f"Tool: {request['tool_name']}"

                logger.warning(
                    f"Retryable error for {request_info} (attempt {attempt + 1}/{self.max_retries + 1}): {exc}. "
                    f"Retrying after {delay:.2f}s..."
                )

                # Wait before retrying
                await asyncio.sleep(delay)
                attempt += 1

        # This should never happen, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Retry logic error: no exception captured")
