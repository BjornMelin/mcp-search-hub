"""Tests for exponential backoff retry functionality."""

from unittest.mock import MagicMock

import httpx
import pytest

from mcp_search_hub.utils.errors import ProviderTimeoutError
from mcp_search_hub.utils.retry import (
    RetryConfig,
    is_retryable_exception,
    retry_async,
    with_exponential_backoff,
)


class TestRetryConfig:
    """Test RetryConfig functionality."""

    def test_default_config(self):
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_custom_config(self):
        """Test custom retry configuration."""
        config = RetryConfig(
            max_retries=5,
            base_delay=0.5,
            max_delay=30.0,
            exponential_base=3.0,
            jitter=False,
        )
        assert config.max_retries == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 30.0
        assert config.exponential_base == 3.0
        assert config.jitter is False

    def test_calculate_delay_without_jitter(self):
        """Test delay calculation without jitter."""
        config = RetryConfig(
            base_delay=1.0, exponential_base=2.0, max_delay=10.0, jitter=False
        )

        # First attempt (0-indexed)
        assert config.calculate_delay(0) == 1.0  # 1 * 2^0 = 1

        # Second attempt
        assert config.calculate_delay(1) == 2.0  # 1 * 2^1 = 2

        # Third attempt
        assert config.calculate_delay(2) == 4.0  # 1 * 2^2 = 4

        # With max delay cap
        assert config.calculate_delay(10) == 10.0  # Would be 1024, but capped at 10

    def test_calculate_delay_with_jitter(self):
        """Test delay calculation with jitter."""
        config = RetryConfig(
            base_delay=1.0, exponential_base=2.0, max_delay=10.0, jitter=True
        )

        # Delays should vary due to jitter (±25%)
        delays = [config.calculate_delay(1) for _ in range(10)]
        assert len(set(delays)) > 1  # Should have some variation
        assert all(1.5 <= d <= 2.5 for d in delays)  # 2.0 ± 25%


class TestRetryableExceptions:
    """Test retryable exception detection."""

    def test_retryable_exceptions(self):
        """Test detection of retryable exceptions."""
        # httpx exceptions
        assert is_retryable_exception(httpx.TimeoutException("timeout"))
        assert is_retryable_exception(httpx.ConnectError("connect error"))
        assert is_retryable_exception(httpx.RemoteProtocolError("protocol error"))

        # Standard exceptions
        assert is_retryable_exception(ConnectionError("connection error"))
        assert is_retryable_exception(TimeoutError("timeout error"))
        assert is_retryable_exception(ProviderTimeoutError("provider timeout", "test"))

        # HTTP status errors
        response_429 = MagicMock()
        response_429.status_code = 429
        assert is_retryable_exception(
            httpx.HTTPStatusError("", request=None, response=response_429)
        )

        response_500 = MagicMock()
        response_500.status_code = 500
        assert is_retryable_exception(
            httpx.HTTPStatusError("", request=None, response=response_500)
        )

        response_503 = MagicMock()
        response_503.status_code = 503
        assert is_retryable_exception(
            httpx.HTTPStatusError("", request=None, response=response_503)
        )

    def test_non_retryable_exceptions(self):
        """Test detection of non-retryable exceptions."""
        # HTTP status errors for client errors
        response_400 = MagicMock()
        response_400.status_code = 400
        assert not is_retryable_exception(
            httpx.HTTPStatusError("", request=None, response=response_400)
        )

        response_401 = MagicMock()
        response_401.status_code = 401
        assert not is_retryable_exception(
            httpx.HTTPStatusError("", request=None, response=response_401)
        )

        response_404 = MagicMock()
        response_404.status_code = 404
        assert not is_retryable_exception(
            httpx.HTTPStatusError("", request=None, response=response_404)
        )

        # Other exceptions
        assert not is_retryable_exception(ValueError("value error"))
        assert not is_retryable_exception(TypeError("type error"))
        assert not is_retryable_exception(KeyError("key error"))


class TestRetryDecorator:
    """Test the retry decorator functionality."""

    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Test that successful calls don't retry."""
        call_count = 0

        @with_exponential_backoff(RetryConfig(max_retries=3))
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_func()
        assert result == "success"
        assert call_count == 1  # Should only be called once

    @pytest.mark.asyncio
    async def test_retry_on_retryable_exception(self):
        """Test retry on retryable exceptions."""
        call_count = 0

        @with_exponential_backoff(
            RetryConfig(max_retries=3, base_delay=0.01)  # Fast for testing
        )
        async def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("timeout")
            return "success"

        result = await failing_func()
        assert result == "success"
        assert call_count == 3  # Should retry twice before succeeding

    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable_exception(self):
        """Test no retry on non-retryable exceptions."""
        call_count = 0

        @with_exponential_backoff(RetryConfig(max_retries=3))
        async def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("non-retryable")

        with pytest.raises(ValueError):
            await failing_func()

        assert call_count == 1  # Should not retry

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """Test that max retries are respected."""
        call_count = 0

        @with_exponential_backoff(
            RetryConfig(max_retries=2, base_delay=0.01)  # Fast for testing
        )
        async def always_failing_func():
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("timeout")

        with pytest.raises(httpx.TimeoutException):
            await always_failing_func()

        assert call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_retry_callback(self):
        """Test that retry callback is called."""
        retry_calls = []

        def on_retry(exc, attempt):
            retry_calls.append((str(exc), attempt))

        @with_exponential_backoff(
            RetryConfig(max_retries=2, base_delay=0.01), on_retry=on_retry
        )
        async def failing_func():
            raise httpx.TimeoutException("timeout")

        with pytest.raises(httpx.TimeoutException):
            await failing_func()

        assert len(retry_calls) == 2  # Called for each retry
        assert retry_calls[0] == ("timeout", 0)
        assert retry_calls[1] == ("timeout", 1)


class TestRetryAsync:
    """Test the retry_async function."""

    @pytest.mark.asyncio
    async def test_retry_async_success(self):
        """Test retry_async with successful function."""

        async def successful_func(value):
            return value * 2

        result = await retry_async(successful_func, 5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_retry_async_with_retries(self):
        """Test retry_async with retries."""
        call_count = 0

        async def sometimes_failing(value):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("timeout")
            return value * 2

        result = await retry_async(
            sometimes_failing, 5, config=RetryConfig(max_retries=3, base_delay=0.01)
        )
        assert result == 10
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_async_with_kwargs(self):
        """Test retry_async with keyword arguments."""

        async def func_with_kwargs(a, b=10):
            return a + b

        result = await retry_async(func_with_kwargs, 5, b=20)
        assert result == 25


class TestIntegrationWithProviders:
    """Test integration with provider retry mixin."""

    @pytest.mark.asyncio
    async def test_provider_with_retry(self):
        """Test a simulated provider using retry logic."""
        from mcp_search_hub.providers.retry_mixin import RetryMixin

        class MockProvider(RetryMixin):
            def __init__(self):
                self.call_count = 0

            async def search_api(self, query):
                self.call_count += 1
                if self.call_count < 3:
                    raise httpx.TimeoutException("API timeout")
                return {"results": [{"title": query}]}

        provider = MockProvider()

        # Wrap the API call with retry
        @provider.with_retry
        async def search_with_retry(query):
            return await provider.search_api(query)

        # Override get_retry_config for faster testing
        provider.get_retry_config = lambda: RetryConfig(max_retries=3, base_delay=0.01)

        result = await search_with_retry("test query")
        assert result == {"results": [{"title": "test query"}]}
        assert provider.call_count == 3
