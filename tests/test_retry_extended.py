"""Extended tests for exponential backoff retry functionality."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mcp_search_hub.utils.errors import SearchError
from mcp_search_hub.utils.retry import (
    RetryConfig,
    is_retryable_exception,
    with_exponential_backoff,
)


class TestEdgeCases:
    """Test edge cases for retry functionality."""

    @pytest.mark.asyncio
    async def test_zero_max_retries(self):
        """Test behavior when max_retries is set to 0."""
        call_count = 0

        @with_exponential_backoff(RetryConfig(max_retries=0))
        async def func():
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("timeout")

        # Should fail immediately without retries
        with pytest.raises(httpx.TimeoutException):
            await func()

        assert call_count == 1  # Only the initial call, no retries

    @pytest.mark.asyncio
    async def test_negative_max_retries(self):
        """Test behavior when max_retries is negative (should be treated as 0)."""
        call_count = 0

        @with_exponential_backoff(RetryConfig(max_retries=-1))
        async def func():
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("timeout")

        # Should fail immediately without retries
        with pytest.raises(httpx.TimeoutException):
            await func()

        assert call_count == 1  # Only the initial call, no retries

    @pytest.mark.asyncio
    async def test_success_after_multiple_failures(self):
        """Test success after multiple failures with different exception types."""
        call_count = 0
        exceptions = [
            httpx.TimeoutException("timeout"),
            httpx.ConnectError("connection error"),
            httpx.RemoteProtocolError("protocol error"),
        ]

        @with_exponential_backoff(RetryConfig(max_retries=3, base_delay=0.01))
        async def func():
            nonlocal call_count
            if call_count < len(exceptions):
                exc = exceptions[call_count]
                call_count += 1
                raise exc
            call_count += 1
            return "success"

        result = await func()
        assert result == "success"
        assert call_count == 4  # 3 failures + 1 success

    @pytest.mark.asyncio
    async def test_failure_with_mixed_exceptions(self):
        """Test failure with mix of retryable and non-retryable exceptions."""
        call_count = 0

        @with_exponential_backoff(RetryConfig(max_retries=3, base_delay=0.01))
        async def func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("timeout")
            if call_count == 2:
                # Non-retryable exception should break the retry loop
                raise ValueError("non-retryable")
            return "success"

        # Should fail with ValueError after first retry
        with pytest.raises(ValueError):
            await func()

        assert call_count == 2  # Initial + 1 retry, then non-retryable exception

    @pytest.mark.asyncio
    async def test_actual_delays(self):
        """Test that actual delays are close to expected values."""
        call_times = []

        @with_exponential_backoff(
            RetryConfig(max_retries=2, base_delay=0.1, jitter=False)
        )
        async def func():
            call_times.append(time.time())
            if len(call_times) <= 2:
                raise httpx.TimeoutException("timeout")
            return "success"

        result = await func()
        assert result == "success"
        assert len(call_times) == 3  # 2 failures + 1 success

        # Verify delays: first call → second call should be ~0.1s (base_delay)
        # second call → third call should be ~0.2s (base_delay * (exponential_base^1))
        assert 0.05 <= call_times[1] - call_times[0] <= 0.15
        assert 0.15 <= call_times[2] - call_times[1] <= 0.25

    @pytest.mark.asyncio
    async def test_retryable_search_error_messages(self):
        """Test that search errors with 'temporary' or 'timeout' are retryable."""
        cases = [
            ("Temporary server error", True),
            ("Server timeout occurred", True),
            ("Search timed out", True),
            ("Invalid query format", False),
            ("Authentication failed", False),
            ("Results not found", False),
        ]

        for message, should_retry in cases:
            error = SearchError(message, provider="test")
            assert is_retryable_exception(error) == should_retry

    @pytest.mark.asyncio
    async def test_concurrent_retries(self):
        """Test multiple concurrent functions with retries."""
        # Track number of calls for each function
        call_counts = [0, 0, 0]

        @with_exponential_backoff(RetryConfig(max_retries=2, base_delay=0.01))
        async def func1():
            call_counts[0] += 1
            if call_counts[0] <= 1:
                raise httpx.TimeoutException("timeout")
            return "result1"

        @with_exponential_backoff(RetryConfig(max_retries=2, base_delay=0.01))
        async def func2():
            call_counts[1] += 1
            if call_counts[1] <= 2:
                raise httpx.ConnectError("connection error")
            return "result2"

        @with_exponential_backoff(RetryConfig(max_retries=2, base_delay=0.01))
        async def func3():
            call_counts[2] += 1
            return "result3"  # Always succeeds

        # Run all functions concurrently
        results = await asyncio.gather(func1(), func2(), func3())

        assert results == ["result1", "result2", "result3"]
        assert call_counts == [2, 3, 1]  # Verify call counts

    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        """Test that delays are capped at max_delay."""
        delays = []

        config = RetryConfig(
            max_retries=5,
            base_delay=1.0,
            exponential_base=10.0,  # Large base to test cap
            max_delay=2.0,  # Low cap
            jitter=False,
        )

        # Capture delays directly
        for attempt in range(5):
            delays.append(config.calculate_delay(attempt))

        # Expected: 1, 2, 2, 2, 2
        # - First attempt: 1.0 * 10^0 = 1.0
        # - Second attempt: 1.0 * 10^1 = 10.0, capped to 2.0
        # - Third+: All capped at 2.0
        assert delays[0] == 1.0
        assert all(d == 2.0 for d in delays[1:])


class TestIntegrationWithHttpClient:
    """Test retry integration with HTTP client."""

    @pytest.mark.asyncio
    async def test_http_client_timeouts(self):
        """Test retry logic with HTTP client timeouts."""
        mock_client = AsyncMock()
        call_count = 0

        # First two calls raise TimeoutError, third succeeds
        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise httpx.TimeoutException("Request timed out")
            return httpx.Response(200, json={"result": "data"})

        mock_client.get.side_effect = side_effect

        @with_exponential_backoff(RetryConfig(max_retries=3, base_delay=0.01))
        async def fetch_data():
            return await mock_client.get("https://example.com/api")

        response = await fetch_data()
        assert response.status_code == 200
        assert call_count == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_http_error_retries(self):
        """Test retry logic with different HTTP errors."""
        mock_client = AsyncMock()
        responses = [
            httpx.Response(429),  # Too Many Requests (retryable)
            httpx.Response(503),  # Service Unavailable (retryable)
            httpx.Response(200, json={"success": True}),  # Success
        ]

        # Set up mock to return different responses on each call
        mock_client.get.side_effect = lambda *args, **kwargs: responses.pop(0)

        @with_exponential_backoff(RetryConfig(max_retries=3, base_delay=0.01))
        async def fetch_data():
            response = await mock_client.get("https://example.com/api")
            response.raise_for_status()
            return response

        # Should retry on 429 and 503, then succeed
        response = await fetch_data()
        assert response.status_code == 200
        assert response.json() == {"success": True}
        assert mock_client.get.call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_http_errors(self):
        """Test that client errors (4xx) don't trigger retries."""
        mock_client = AsyncMock()

        # Create a 404 response
        response_404 = httpx.Response(404)
        # Note: HTTPStatusError will be raised by response.raise_for_status()

        # Set up side effect to raise the error
        mock_client.get.side_effect = lambda *args, **kwargs: responses.pop(0)
        responses = [response_404]

        @with_exponential_backoff(RetryConfig(max_retries=3, base_delay=0.01))
        async def fetch_data():
            response = await mock_client.get("https://example.com/api")
            response.raise_for_status()
            return response

        # 404 should not trigger retries, so this should fail immediately
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await fetch_data()

        assert exc_info.value.response.status_code == 404
        assert mock_client.get.call_count == 1  # Only called once


class TestLoggingBehavior:
    """Test logging behavior during retries."""

    @pytest.mark.asyncio
    async def test_retry_logging(self):
        """Test that appropriate log messages are generated during retries."""
        with patch("mcp_search_hub.utils.retry.logger") as mock_logger:
            call_count = 0

            @with_exponential_backoff(
                RetryConfig(max_retries=2, base_delay=0.01, jitter=False)
            )
            async def failing_func():
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise httpx.TimeoutException("timeout")
                return "success"

            result = await failing_func()
            assert result == "success"

            # Check warning logs for each retry
            assert mock_logger.warning.call_count == 2
            # Verify first retry log message
            warning_args = mock_logger.warning.call_args_list[0][0][0]
            assert "Retryable error in failing_func (attempt 1/3)" in warning_args
            assert "timeout" in warning_args
            assert "Retrying after 0.01s" in warning_args

            # Verify second retry log message
            warning_args = mock_logger.warning.call_args_list[1][0][0]
            assert "Retryable error in failing_func (attempt 2/3)" in warning_args
            assert "Retrying after 0.02s" in warning_args

    @pytest.mark.asyncio
    async def test_retry_exhaustion_logging(self):
        """Test logging when all retries are exhausted."""
        with patch("mcp_search_hub.utils.retry.logger") as mock_logger:

            @with_exponential_backoff(RetryConfig(max_retries=2, base_delay=0.01))
            async def always_failing():
                raise httpx.TimeoutException("persistent timeout")

            with pytest.raises(httpx.TimeoutException):
                await always_failing()

            # Verify warning logs for each retry plus final error log
            assert mock_logger.warning.call_count == 2
            assert mock_logger.error.call_count == 1

            # Check error log for retry exhaustion
            error_args = mock_logger.error.call_args[0][0]
            assert "All retry attempts exhausted for always_failing" in error_args
            assert "persistent timeout" in error_args

    @pytest.mark.asyncio
    async def test_non_retryable_logging(self):
        """Test logging for non-retryable exceptions."""
        with patch("mcp_search_hub.utils.retry.logger") as mock_logger:

            @with_exponential_backoff(RetryConfig(max_retries=2))
            async def non_retryable_func():
                raise ValueError("bad value")

            with pytest.raises(ValueError):
                await non_retryable_func()

            # Should log a debug message for non-retryable exception
            assert mock_logger.debug.call_count == 1
            debug_args = mock_logger.debug.call_args[0][0]
            assert "Non-retryable exception in non_retryable_func" in debug_args
            assert "bad value" in debug_args

            # No warning logs for retries should be present
            assert mock_logger.warning.call_count == 0
