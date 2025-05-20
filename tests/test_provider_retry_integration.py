"""Integration tests for retry functionality with provider implementations."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.providers.exa_mcp import ExaMCPProvider
from mcp_search_hub.providers.firecrawl_mcp import FirecrawlMCPProvider
from mcp_search_hub.providers.linkup_mcp import LinkupMCPProvider
from mcp_search_hub.providers.perplexity_mcp import PerplexityMCPProvider
from mcp_search_hub.providers.retry_mixin import RetryMixin
from mcp_search_hub.providers.tavily_mcp import TavilyMCPProvider
from mcp_search_hub.utils.retry import RetryConfig


class TestRetryMixinIntegration:
    """Test the integration of RetryMixin with provider implementations."""

    def test_all_providers_use_retry_mixin(self):
        """Verify that all search providers inherit from RetryMixin."""
        providers = [
            ExaMCPProvider,
            FirecrawlMCPProvider,
            LinkupMCPProvider,
            PerplexityMCPProvider,
            TavilyMCPProvider,
        ]

        for provider_class in providers:
            assert issubclass(provider_class, RetryMixin), (
                f"{provider_class.__name__} should inherit from RetryMixin"
            )


class TestLinkupRetryIntegration:
    """Test the retry functionality in the LinkupMCPProvider."""

    @pytest.mark.asyncio
    async def test_linkup_search_with_retry(self):
        """Test that search calls are wrapped with retry logic."""
        # Create provider with mock configuration
        with patch("mcp_search_hub.providers.linkup_mcp.GenericMCPProvider"):
            provider = LinkupMCPProvider(api_key="test_key")

            # Mock the with_retry method
            original_with_retry = provider.with_retry
            retry_spy = MagicMock()

            # Create a mock decorator that captures the function being decorated
            def mock_with_retry(func):
                retry_spy(func.__name__)
                return original_with_retry(func)

            provider.with_retry = mock_with_retry

            # Mock super().search to avoid actual API calls
            with patch(
                "mcp_search_hub.providers.generic_mcp.GenericMCPProvider.search",
                return_value={"results": []},
            ):
                # Call the search method
                query = SearchQuery(query="test")
                await provider.search(query)

                # Verify that super().search was wrapped with retry
                retry_spy.assert_called_once_with("search")


class TestProviderRetryConfigurations:
    """Test the retry configuration for all providers."""

    @pytest.mark.parametrize(
        "provider_class",
        [
            ExaMCPProvider,
            FirecrawlMCPProvider,
            LinkupMCPProvider,
            PerplexityMCPProvider,
            TavilyMCPProvider,
        ],
    )
    def test_provider_retry_config(self, provider_class):
        """Test that providers can get retry configuration from settings."""
        # Create provider with mock configuration
        with patch(
            "mcp_search_hub.providers.retry_mixin.get_settings"
        ) as mock_settings:
            # Mock the settings
            mock_config = MagicMock()
            mock_config.retry.max_retries = 3
            mock_config.retry.base_delay = 1.5
            mock_config.retry.max_delay = 45.0
            mock_config.retry.exponential_base = 2.5
            mock_config.retry.jitter = True
            mock_settings.return_value = mock_config

            # Create provider instance
            with patch(
                f"mcp_search_hub.providers.{provider_class.__name__.lower()}.GenericMCPProvider"
            ):
                provider = provider_class(api_key="test_key")

                # Get retry config
                retry_config = provider.get_retry_config()

                # Verify config matches settings
                assert retry_config.max_retries == 3
                assert retry_config.base_delay == 1.5
                assert retry_config.max_delay == 45.0
                assert retry_config.exponential_base == 2.5
                assert retry_config.jitter is True


class TestRetryInvocationWithErrors:
    """Test that retries are actually invoked when errors occur."""

    @pytest.mark.asyncio
    async def test_provider_retries_on_timeout(self):
        """Test that provider retries on timeout errors."""
        # Mock the retry.py module to avoid actual waiting
        with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
            # Create a mock provider for testing
            class MockTimeoutProvider(RetryMixin):
                def __init__(self):
                    self.call_count = 0

                def get_retry_config(self):
                    return RetryConfig(max_retries=2, base_delay=0.01, jitter=False)

                async def api_call(self, query):
                    """Simulate an API call that times out twice then succeeds."""
                    self.call_count += 1
                    if self.call_count <= 2:
                        raise httpx.TimeoutException("API timeout")
                    return {"results": [{"title": query}]}

            provider = MockTimeoutProvider()

            # Wrap the API call with retry
            @provider.with_retry
            async def search_with_retry(query):
                return await provider.api_call(query)

            # Call the wrapped method
            result = await search_with_retry("test query")

            # Verify it was called the expected number of times
            assert provider.call_count == 3  # Initial + 2 retries
            assert result == {"results": [{"title": "test query"}]}

    @pytest.mark.asyncio
    async def test_provider_retries_on_connection_error(self):
        """Test that provider retries on connection errors."""
        # Mock the retry.py module to avoid actual waiting
        with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
            # Create a mock provider for testing
            class MockConnectionErrorProvider(RetryMixin):
                def __init__(self):
                    self.call_count = 0

                def get_retry_config(self):
                    return RetryConfig(max_retries=2, base_delay=0.01, jitter=False)

                async def api_call(self, query):
                    """Simulate an API call that has connection errors twice then succeeds."""
                    self.call_count += 1
                    if self.call_count <= 2:
                        raise httpx.ConnectError("Connection refused")
                    return {"results": [{"title": query}]}

            provider = MockConnectionErrorProvider()

            # Wrap the API call with retry
            @provider.with_retry
            async def search_with_retry(query):
                return await provider.api_call(query)

            # Call the wrapped method
            result = await search_with_retry("test query")

            # Verify it was called the expected number of times
            assert provider.call_count == 3  # Initial + 2 retries
            assert result == {"results": [{"title": "test query"}]}

    @pytest.mark.asyncio
    async def test_provider_retries_on_server_error(self):
        """Test that provider retries on server errors."""
        # Mock the retry.py module to avoid actual waiting
        with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
            # Create a mock provider for testing
            class MockServerErrorProvider(RetryMixin):
                def __init__(self):
                    self.call_count = 0

                def get_retry_config(self):
                    return RetryConfig(max_retries=2, base_delay=0.01, jitter=False)

                async def api_call(self, query):
                    """Simulate an API call that returns 500 errors twice then succeeds."""
                    self.call_count += 1
                    if self.call_count <= 2:
                        response = MagicMock()
                        response.status_code = 500
                        raise httpx.HTTPStatusError(
                            "Internal Server Error",
                            request=MagicMock(),
                            response=response,
                        )
                    return {"results": [{"title": query}]}

            provider = MockServerErrorProvider()

            # Wrap the API call with retry
            @provider.with_retry
            async def search_with_retry(query):
                return await provider.api_call(query)

            # Call the wrapped method
            result = await search_with_retry("test query")

            # Verify it was called the expected number of times
            assert provider.call_count == 3  # Initial + 2 retries
            assert result == {"results": [{"title": "test query"}]}

    @pytest.mark.asyncio
    async def test_provider_retries_on_rate_limit(self):
        """Test that provider retries on rate limit (429) errors."""
        # Mock the retry.py module to avoid actual waiting
        with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
            # Create a mock provider for testing
            class MockRateLimitProvider(RetryMixin):
                def __init__(self):
                    self.call_count = 0

                def get_retry_config(self):
                    return RetryConfig(max_retries=2, base_delay=0.01, jitter=False)

                async def api_call(self, query):
                    """Simulate an API call that returns 429 errors twice then succeeds."""
                    self.call_count += 1
                    if self.call_count <= 2:
                        response = MagicMock()
                        response.status_code = 429
                        response.headers = {"Retry-After": "1"}
                        raise httpx.HTTPStatusError(
                            "Too Many Requests", request=MagicMock(), response=response
                        )
                    return {"results": [{"title": query}]}

            provider = MockRateLimitProvider()

            # Wrap the API call with retry
            @provider.with_retry
            async def search_with_retry(query):
                return await provider.api_call(query)

            # Call the wrapped method
            result = await search_with_retry("test query")

            # Verify it was called the expected number of times
            assert provider.call_count == 3  # Initial + 2 retries
            assert result == {"results": [{"title": "test query"}]}

    @pytest.mark.asyncio
    async def test_provider_no_retry_on_client_error(self):
        """Test that provider doesn't retry on client errors (4xx except 429)."""
        # Mock the retry.py module to avoid actual waiting
        with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
            # Create a mock provider for testing
            class MockClientErrorProvider(RetryMixin):
                def __init__(self):
                    self.call_count = 0

                def get_retry_config(self):
                    return RetryConfig(max_retries=2, base_delay=0.01, jitter=False)

                async def api_call(self, query):
                    """Simulate an API call that returns a 400 error (non-retryable)."""
                    self.call_count += 1
                    response = MagicMock()
                    response.status_code = 400
                    raise httpx.HTTPStatusError(
                        "Bad Request", request=MagicMock(), response=response
                    )

            provider = MockClientErrorProvider()

            # Wrap the API call with retry
            @provider.with_retry
            async def search_with_retry(query):
                return await provider.api_call(query)

            # Call the wrapped method, should fail immediately with no retries
            with pytest.raises(httpx.HTTPStatusError):
                await search_with_retry("test query")

            # Verify it was only called once (no retries)
            assert provider.call_count == 1


class TestEexaMCPProviderRetry:
    """Test retry functionality in ExaMCPProvider."""

    @pytest.mark.asyncio
    async def test_exa_search_retry(self):
        """Test that ExaMCPProvider uses retry correctly."""
        with patch(
            "mcp_search_hub.providers.exa_mcp.GenericMCPProvider"
        ) as mock_generic:
            # Create a mock that fails twice then succeeds
            mock_search = AsyncMock()
            call_count = 0

            async def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise httpx.TimeoutException("Search timed out")
                return {"results": [{"title": "Exa result"}]}

            mock_search.side_effect = side_effect
            mock_generic.return_value.search = mock_search

            # Create provider and override retry config for faster testing
            provider = ExaMCPProvider(api_key="test_key")
            provider.get_retry_config = lambda: RetryConfig(
                max_retries=3, base_delay=0.01
            )

            # Mock sleep to avoid actual waiting
            with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
                query = SearchQuery(query="test")
                await provider.search(query)

                # Verify retry behavior
                assert call_count == 3  # Initial + 2 retries
                assert mock_search.call_count == 3


class TestFirecrawlMCPProviderRetry:
    """Test retry functionality in FirecrawlMCPProvider."""

    @pytest.mark.asyncio
    async def test_firecrawl_search_retry(self):
        """Test that FirecrawlMCPProvider uses retry correctly."""
        with patch(
            "mcp_search_hub.providers.firecrawl_mcp.GenericMCPProvider"
        ) as mock_generic:
            # Create a mock that fails twice then succeeds
            mock_search = AsyncMock()
            call_count = 0

            async def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise httpx.TimeoutException("Search timed out")
                return {"results": [{"title": "Firecrawl result"}]}

            mock_search.side_effect = side_effect
            mock_generic.return_value.search = mock_search

            # Create provider and override retry config for faster testing
            provider = FirecrawlMCPProvider(api_key="test_key")
            provider.get_retry_config = lambda: RetryConfig(
                max_retries=3, base_delay=0.01
            )

            # Mock sleep to avoid actual waiting
            with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
                query = SearchQuery(query="test")
                await provider.search(query)

                # Verify retry behavior
                assert call_count == 3  # Initial + 2 retries
                assert mock_search.call_count == 3


class TestPerplexityMCPProviderRetry:
    """Test retry functionality in PerplexityMCPProvider."""

    @pytest.mark.asyncio
    async def test_perplexity_search_retry(self):
        """Test that PerplexityMCPProvider uses retry correctly."""
        with patch(
            "mcp_search_hub.providers.perplexity_mcp.GenericMCPProvider"
        ) as mock_generic:
            # Create a mock that fails twice then succeeds
            mock_search = AsyncMock()
            call_count = 0

            async def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise httpx.TimeoutException("Search timed out")
                return {"results": [{"title": "Perplexity result"}]}

            mock_search.side_effect = side_effect
            mock_generic.return_value.search = mock_search

            # Create provider and override retry config for faster testing
            provider = PerplexityMCPProvider(api_key="test_key")
            provider.get_retry_config = lambda: RetryConfig(
                max_retries=3, base_delay=0.01
            )

            # Mock sleep to avoid actual waiting
            with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
                query = SearchQuery(query="test")
                await provider.search(query)

                # Verify retry behavior
                assert call_count == 3  # Initial + 2 retries
                assert mock_search.call_count == 3


class TestTavilyMCPProviderRetry:
    """Test retry functionality in TavilyMCPProvider."""

    @pytest.mark.asyncio
    async def test_tavily_search_retry(self):
        """Test that TavilyMCPProvider uses retry correctly."""
        with patch(
            "mcp_search_hub.providers.tavily_mcp.GenericMCPProvider"
        ) as mock_generic:
            # Create a mock that fails twice then succeeds
            mock_search = AsyncMock()
            call_count = 0

            async def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise httpx.TimeoutException("Search timed out")
                return {"results": [{"title": "Tavily result"}]}

            mock_search.side_effect = side_effect
            mock_generic.return_value.search = mock_search

            # Create provider and override retry config for faster testing
            provider = TavilyMCPProvider(api_key="test_key")
            provider.get_retry_config = lambda: RetryConfig(
                max_retries=3, base_delay=0.01
            )

            # Mock sleep to avoid actual waiting
            with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
                query = SearchQuery(query="test")
                await provider.search(query)

                # Verify retry behavior
                assert call_count == 3  # Initial + 2 retries
                assert mock_search.call_count == 3


class TestMixedExceptionRetry:
    """Test retry with a mix of different exception types."""

    @pytest.mark.asyncio
    async def test_retry_with_mixed_exceptions(self):
        """Test retry with a sequence of different exception types."""
        with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):

            class MockMixedExceptionProvider(RetryMixin):
                def __init__(self):
                    self.call_count = 0

                def get_retry_config(self):
                    return RetryConfig(max_retries=3, base_delay=0.01, jitter=False)

                async def api_call(self, query):
                    """Simulate an API call that fails with different exceptions then succeeds."""
                    self.call_count += 1

                    if self.call_count == 1:
                        raise httpx.TimeoutException("Timeout")
                    if self.call_count == 2:
                        raise httpx.ConnectError("Connection refused")
                    if self.call_count == 3:
                        response = MagicMock()
                        response.status_code = 503
                        raise httpx.HTTPStatusError(
                            "Service Unavailable",
                            request=MagicMock(),
                            response=response,
                        )

                    return {"results": [{"title": query}]}

            provider = MockMixedExceptionProvider()

            # Wrap the API call with retry
            @provider.with_retry
            async def search_with_retry(query):
                return await provider.api_call(query)

            # Should exhaust all retries and fail
            with pytest.raises(httpx.HTTPStatusError):
                await search_with_retry("test query")

            # Verify it was called the expected number of times
            assert provider.call_count == 4  # Initial + 3 retries
