"""Exponential backoff retry logic for API calls."""

import asyncio
import random
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

import httpx

from ..utils.errors import ProviderTimeoutError, SearchError
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
        self.max_retries = max_retries
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

    # Check if it's a search error that might be retryable
    if isinstance(exc, SearchError):
        # Only retry if it's a temporary error
        return "temporary" in str(exc).lower() or "timeout" in str(exc).lower()

    return False


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

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc

                    # Check if this is the last attempt
                    if attempt >= config.max_retries:
                        logger.error(
                            f"All retry attempts exhausted for {func.__name__}: {exc}"
                        )
                        raise

                    # Check if the exception is retryable
                    if not is_retryable_exception(exc):
                        logger.debug(
                            f"Non-retryable exception in {func.__name__}: {exc}"
                        )
                        raise

                    # Calculate delay for next attempt
                    delay = config.calculate_delay(attempt)

                    logger.warning(
                        f"Retryable error in {func.__name__} (attempt {attempt + 1}/{config.max_retries + 1}): {exc}. "
                        f"Retrying after {delay:.2f}s..."
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

    for attempt in range(config.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            last_exception = exc

            # Check if this is the last attempt
            if attempt >= config.max_retries:
                logger.error(f"All retry attempts exhausted for {func.__name__}: {exc}")
                raise

            # Check if the exception is retryable
            if not is_retryable_exception(exc):
                logger.debug(f"Non-retryable exception in {func.__name__}: {exc}")
                raise

            # Calculate delay for next attempt
            delay = config.calculate_delay(attempt)

            logger.warning(
                f"Retryable error in {func.__name__} (attempt {attempt + 1}/{config.max_retries + 1}): {exc}. "
                f"Retrying after {delay:.2f}s..."
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
