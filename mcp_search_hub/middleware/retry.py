"""Retry middleware for HTTP requests.

This middleware adds exponential backoff retry logic to HTTP requests
when certain types of transient failures occur.
"""

import asyncio
import random
from collections.abc import Callable

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..utils.errors import ProviderTimeoutError, SearchError
from ..utils.logging import get_logger

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


class RetryMiddleware(BaseHTTPMiddleware):
    """Middleware for applying exponential backoff retry logic."""

    def __init__(self, app, **options):
        """Initialize retry middleware.

        Args:
            app: ASGI application
            **options: Configuration options including:
                - max_retries: Maximum number of retry attempts
                - base_delay: Initial delay between retries in seconds
                - max_delay: Maximum delay between retries in seconds
                - exponential_base: Base for exponential backoff calculation
                - jitter: Whether to add randomization to delays
                - skip_paths: List of paths to skip retry logic
        """
        super().__init__(app)
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

    def should_retry_request(self, request: Request) -> bool:
        """Determine if a request should be retried.

        Args:
            request: The HTTP request to check

        Returns:
            True if the request should be handled by retry logic
        """
        # Check if path is in skip list
        path = request.url.path
        return path not in self.skip_paths

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process HTTP requests with retry logic.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or handler

        Returns:
            The response from downstream
        """
        # Check if we should apply retry logic to this request
        if not self.should_retry_request(request):
            # Skip retry logic for excluded paths
            return await call_next(request)

        # Initialize retry state
        attempt = 0
        last_exception = None

        # Retry loop
        while attempt <= self.max_retries:
            try:
                # Store retry attempt in request state
                request.state.retry_attempt = attempt

                # Call the next middleware/handler and return on success
                return await call_next(request)

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
                request_info = f"{request.method} {request.url.path}"

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
