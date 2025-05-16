"""Mixin for adding retry functionality to providers."""

from ..config import get_settings
from ..utils.retry import RetryConfig, with_exponential_backoff


class RetryMixin:
    """Mixin to add retry functionality to providers."""

    def get_retry_config(self) -> RetryConfig:
        """Get retry configuration from settings.

        Returns:
            RetryConfig instance with settings from environment
        """
        settings = get_settings()
        return RetryConfig(
            max_retries=settings.retry.max_retries,
            base_delay=settings.retry.base_delay,
            max_delay=settings.retry.max_delay,
            exponential_base=settings.retry.exponential_base,
            jitter=settings.retry.jitter,
        )

    def with_retry(self, func):
        """Decorator to add retry logic to a method.

        Args:
            func: The async function to wrap with retry logic

        Returns:
            Wrapped function with exponential backoff retry
        """
        return with_exponential_backoff(config=self.get_retry_config())(func)
