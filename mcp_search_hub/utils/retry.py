"""Exponential backoff retry logic for API calls."""

import asyncio
import random
import time
import traceback
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

import httpx

from ..utils.errors import (
    NetworkConnectionError,
    NetworkTimeoutError,
    ProviderRateLimitError,
    ProviderServiceError,
    ProviderTimeoutError,
    SearchError,
)
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Type var for generic async function
T = TypeVar("T")
AsyncFunc = TypeVar("AsyncFunc", bound=Callable[..., Any])

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
    NetworkConnectionError,
    NetworkTimeoutError,
)


class RetryConfig:
    """Configuration for exponential backoff retry."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        """Initialize retry configuration.

        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Initial delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
            exponential_base: Base for exponential backoff calculation
            jitter: Whether to add randomization to delays
        """
        self.max_retries = max(0, max_retries)  # Ensure non-negative
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given retry attempt.

        Args:
            attempt: Current retry attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff calculation
        delay = min(self.base_delay * (self.exponential_base**attempt), self.max_delay)

        if self.jitter:
            # Add ±25% jitter
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)  # Ensure non-negative


def is_retryable_exception(exc: Exception) -> bool:
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

    # Check for specific provider error types that are retryable
    if isinstance(exc, ProviderTimeoutError):
        return True

    # Rate limits are retryable
    if isinstance(exc, ProviderRateLimitError):
        return True

    # Network errors are generally retryable
    if isinstance(exc, NetworkConnectionError | NetworkTimeoutError):
        return True

    # Service errors can be retryable if they're temporary
    if isinstance(exc, ProviderServiceError):
        # Check the status code if available
        if hasattr(exc, "status_code") and exc.status_code in RETRYABLE_STATUS_CODES:
            return True
        # Check for temporary indicators in message
        if any(
            keyword in str(exc).lower()
            for keyword in ["temporary", "timeout", "retry", "overloaded", "busy"]
        ):
            return True

    # For general SearchErrors, be more cautious
    if isinstance(exc, SearchError):
        # Only retry if it's a temporary error
        return any(
            keyword in str(exc).lower()
            for keyword in ["temporary", "timeout", "retry", "overloaded", "busy"]
        )

    return False


def format_exception_for_log(exc: Exception) -> str:
    """Format exception details for logging.

    Args:
        exc: Exception to format

    Returns:
        Formatted exception string with type and details
    """
    exception_type = type(exc).__name__
    exception_details = str(exc)

    # Handle SearchError and subclasses with detailed formatting
    if isinstance(exc, SearchError):
        details_str = ""

        # Add provider information if available
        if hasattr(exc, "provider") and exc.provider:
            details_str += f" [Provider: {exc.provider}]"

        # Add status code if available
        if hasattr(exc, "status_code"):
            details_str += f" [Status: {exc.status_code}]"

        # Add operation information for timeout errors
        if isinstance(exc, ProviderTimeoutError) and hasattr(exc, "details"):
            if "operation" in exc.details:
                details_str += f" [Operation: {exc.details['operation']}]"
            if "timeout_seconds" in exc.details:
                details_str += f" [Timeout: {exc.details['timeout_seconds']}s]"

        # Add rate limit information
        if isinstance(exc, ProviderRateLimitError) and hasattr(exc, "details"):
            if "limit_type" in exc.details:
                details_str += f" [Limit: {exc.details['limit_type']}]"
            if "retry_after_seconds" in exc.details:
                details_str += f" [Retry-After: {exc.details['retry_after_seconds']}s]"

        # If we have details, include them
        if details_str:
            exception_details = f"{exception_details}{details_str}"

        # Include original error type if wrapped
        if hasattr(exc, "original_error") and exc.original_error:
            orig_type = type(exc.original_error).__name__
            exception_details = f"{exception_details} (Original: {orig_type}: {str(exc.original_error)})"

    # Add HTTP status code if available
    elif isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        reason = exc.response.reason_phrase
        exception_details = f"HTTP {status_code} {reason}: {exception_details}"

        # Add useful headers if they exist
        headers = exc.response.headers
        if "retry-after" in headers:
            exception_details += f" (Retry-After: {headers['retry-after']})"

    # Add timeout information if it's a timeout exception
    elif isinstance(exc, httpx.TimeoutException):
        # Just include the exception string, don't try to access request
        # (it might not be set in test mocks)
        pass

    return f"{exception_type}: {exception_details}"


def log_retry_attempt(
    func_name: str,
    exc: Exception,
    attempt: int,
    max_retries: int,
    delay: float,
    request_info: dict | None = None,
) -> None:
    """Log information about a retry attempt.

    Args:
        func_name: Name of the function being retried
        exc: Exception that triggered the retry
        attempt: Current attempt number (0-indexed)
        max_retries: Maximum number of retry attempts
        delay: Delay before next attempt in seconds
        request_info: Optional dictionary with request information
    """
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    exception_details = format_exception_for_log(exc)

    # Build log message
    log_message = [
        f"Retryable error in {func_name} (attempt {attempt + 1}/{max_retries + 1})",
        f"Time: {current_time}",
        f"Error: {exception_details}",
        f"Retrying after {delay:.2f}s...",
    ]

    # Add request info if available
    if request_info:
        if "url" in request_info:
            log_message.append(f"URL: {request_info['url']}")
        if "method" in request_info:
            log_message.append(f"Method: {request_info['method']}")

    # Join all parts with newlines for structured logging
    logger.warning("\n".join(log_message))

    # For debugging in development, include stack trace at DEBUG level
    if logger.isEnabledFor(10):  # DEBUG level
        stack_trace = "".join(traceback.format_tb(exc.__traceback__))
        logger.debug(f"Retry stack trace for {func_name}:\n{stack_trace}")


def with_exponential_backoff(
    config: RetryConfig | None = None,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[AsyncFunc], AsyncFunc]:
    """Decorator for adding exponential backoff retry to async functions.

    Args:
        config: Retry configuration (uses defaults if None)
        on_retry: Optional callback called on each retry with (exception, attempt)

    Returns:
        Decorated function with retry logic
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: AsyncFunc) -> AsyncFunc:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            start_time = time.time()
            request_info = {}

            # Try to extract request info if this is an HTTP request
            if hasattr(func, "__name__") and "http" in func.__name__.lower():
                # Check for URL in arguments
                for arg in args:
                    if isinstance(arg, str) and (
                        arg.startswith(("http://", "https://"))
                    ):
                        request_info["url"] = arg
                        break

                # Check for method and URL in kwargs
                if "method" in kwargs:
                    request_info["method"] = kwargs["method"]
                if "url" in kwargs:
                    request_info["url"] = kwargs["url"]

            for attempt in range(config.max_retries + 1):
                try:
                    result = await func(*args, **kwargs)

                    # Log success after retries if there were previous attempts
                    if attempt > 0:
                        total_time = time.time() - start_time
                        logger.info(
                            f"Successfully completed {func.__name__} after {attempt} "
                            f"retries in {total_time:.2f}s"
                        )

                    return result

                except Exception as exc:
                    last_exception = exc

                    # Check if this is the last attempt
                    if attempt >= config.max_retries:
                        total_time = time.time() - start_time
                        logger.error(
                            f"All retry attempts exhausted for {func.__name__} after "
                            f"{total_time:.2f}s: {format_exception_for_log(exc)}"
                        )
                        raise

                    # Check if the exception is retryable
                    if not is_retryable_exception(exc):
                        logger.debug(
                            f"Non-retryable exception in {func.__name__}: "
                            f"{format_exception_for_log(exc)}"
                        )
                        raise

                    # Calculate delay for next attempt
                    delay = config.calculate_delay(attempt)

                    # Detailed logging
                    log_retry_attempt(
                        func.__name__,
                        exc,
                        attempt,
                        config.max_retries,
                        delay,
                        request_info,
                    )

                    # Call retry callback if provided
                    if on_retry:
                        on_retry(exc, attempt)

                    # Wait before retrying
                    await asyncio.sleep(delay)

            # This should never happen, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic error: no exception captured")

        return cast(AsyncFunc, wrapper)

    return decorator


async def retry_async(
    func: Callable[..., T],
    *args: Any,
    config: RetryConfig | None = None,
    on_retry: Callable[[Exception, int], None] | None = None,
    **kwargs: Any,
) -> T:
    """Execute an async function with exponential backoff retry.

    Args:
        func: Async function to execute
        *args: Positional arguments for the function
        config: Retry configuration (uses defaults if None)
        on_retry: Optional callback called on each retry with (exception, attempt)
        **kwargs: Keyword arguments for the function

    Returns:
        Result of the function call

    Raises:
        The last exception if all retries are exhausted
    """
    if config is None:
        config = RetryConfig()

    last_exception: Exception | None = None
    start_time = time.time()
    request_info = {}

    # Try to extract request info for HTTP requests
    if hasattr(func, "__name__") and "http" in func.__name__.lower():
        # Try to find URLs in args or kwargs
        for arg in args:
            if isinstance(arg, str) and (arg.startswith(("http://", "https://"))):
                request_info["url"] = arg
                break

        # Check kwargs
        if "url" in kwargs:
            request_info["url"] = kwargs["url"]
        if "method" in kwargs:
            request_info["method"] = kwargs["method"]

    for attempt in range(config.max_retries + 1):
        try:
            result = await func(*args, **kwargs)

            # Log success after retries if there were previous attempts
            if attempt > 0:
                total_time = time.time() - start_time
                logger.info(
                    f"Successfully completed {func.__name__} after {attempt} "
                    f"retries in {total_time:.2f}s"
                )

            return result

        except Exception as exc:
            last_exception = exc

            # Check if this is the last attempt
            if attempt >= config.max_retries:
                total_time = time.time() - start_time
                logger.error(
                    f"All retry attempts exhausted for {func.__name__} after "
                    f"{total_time:.2f}s: {format_exception_for_log(exc)}"
                )
                raise

            # Check if the exception is retryable
            if not is_retryable_exception(exc):
                logger.debug(
                    f"Non-retryable exception in {func.__name__}: "
                    f"{format_exception_for_log(exc)}"
                )
                raise

            # Calculate delay for next attempt
            delay = config.calculate_delay(attempt)

            # Detailed logging
            log_retry_attempt(
                func.__name__,
                exc,
                attempt,
                config.max_retries,
                delay,
                request_info,
            )

            # Call retry callback if provided
            if on_retry:
                on_retry(exc, attempt)

            # Wait before retrying
            await asyncio.sleep(delay)

    # This should never happen, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic error: no exception captured")
