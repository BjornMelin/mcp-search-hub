"""Integration tests for retry functionality with provider implementations."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.providers.base_mcp import BaseMCPProvider
from mcp_search_hub.providers.exa_mcp import ExaMCPProvider
from mcp_search_hub.providers.firecrawl_mcp import FirecrawlMCPProvider
from mcp_search_hub.providers.linkup_mcp import LinkupMCPProvider
from mcp_search_hub.providers.perplexity_mcp import PerplexityMCPProvider
from mcp_search_hub.providers.tavily_mcp import TavilyMCPProvider
from mcp_search_hub.utils.retry import RetryConfig


class TestProviderRetryIntegration:
    """Test the integration of retry functionality in provider implementations."""

    def test_all_providers_have_retry_capability(self):
        """Verify that all search providers have retry capability through BaseMCPProvider."""
        providers = [
            ExaMCPProvider,
            FirecrawlMCPProvider,
            LinkupMCPProvider,
            PerplexityMCPProvider,
            TavilyMCPProvider,
        ]

        for provider_class in providers:
            # Verify they inherit from BaseMCPProvider which has retry functionality
            assert issubclass(provider_class, BaseMCPProvider), (
                f"{provider_class.__name__} should inherit from BaseMCPProvider"
            )

            # Create an instance with mocked dependencies to verify method availability
            with patch(
                f"mcp_search_hub.providers.{provider_class.__name__.lower()}.GenericMCPProvider"
            ):
                provider = provider_class(api_key="test_key")
                assert hasattr(provider, "with_retry"), (
                    f"{provider_class.__name__} should have with_retry method"
                )
                assert hasattr(provider, "get_retry_config"), (
                    f"{provider_class.__name__} should have get_retry_config method"
                )


class TestBaseMCPProviderRetry:
    """Test the retry functionality built into BaseMCPProvider."""

    @pytest.mark.asyncio
    async def test_base_search_with_retry(self):
        """Test that search calls are wrapped with retry logic."""
        # Create a provider with mock configuration
        with patch(
            "mcp_search_hub.providers.generic_mcp.GenericMCPProvider.__init__",
            return_value=None,
        ):
            provider = LinkupMCPProvider(api_key="test_key")
            provider.name = "test_provider"
            provider.RETRY_ENABLED = True

            # Mock the with_retry method
            retry_spy = MagicMock()

            # Create a mock decorator that captures the function being decorated
            def mock_with_retry(func):
                retry_spy(func.__name__)
                return (
                    func  # Just return the original function without actual retry logic
                )

            provider.with_retry = mock_with_retry

            # We need to patch both the superclass search and the provider's search to avoid recursion
            with patch(
                "mcp_search_hub.providers.base_mcp.BaseMCPProvider.search"
            ) as mock_base_search:
                mock_base_search.return_value = {"results": []}

                # Mock the actual search implementation to return a result
                with patch("mcp_search_hub.providers.base_mcp.SearchProvider.search"):
                    # Call the search method
                    query = SearchQuery(query="test")
                    await provider.search(query)

                    # Verify that retry was applied
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
        """Test that providers have configuration-based retry settings."""
        # Create provider with mock configuration
        with patch(
            "mcp_search_hub.providers.generic_mcp.PROVIDER_CONFIGS"
        ) as mock_configs:
            provider_name = provider_class.__name__.replace("MCPProvider", "").lower()
            # Set up a mock provider config
            mock_configs.get.return_value = {
                "env_var": f"{provider_name.upper()}_API_KEY",
                "server_type": "nodejs",
                "package": f"{provider_name}-mcp",
                "tool_name": f"{provider_name}_search",
                "timeout": 10000,
                "retry_config": RetryConfig(
                    max_retries=4,
                    base_delay=2.0,
                    max_delay=30.0,
                    exponential_base=2.5,
                    jitter=0.2,
                ),
                "retry_enabled": True,
            }

            # Create provider instance with mocked dependencies
            with patch(
                f"mcp_search_hub.providers.{provider_class.__name__.lower()}.GenericMCPProvider.__init__",
                return_value=None,
            ):
                provider = provider_class(api_key="test_key")
                provider._retry_config = RetryConfig(
                    max_retries=4,
                    base_delay=2.0,
                    max_delay=30.0,
                    exponential_base=2.5,
                    jitter=0.2,
                )

                # Get retry config
                retry_config = provider.get_retry_config()

                # Verify config matches expected values
                assert retry_config.max_retries == 4
                assert retry_config.base_delay == 2.0
                assert retry_config.max_delay == 30.0
                assert retry_config.exponential_base == 2.5
                assert retry_config.jitter == 0.2


class TestRetryInvocationWithErrors:
    """Test that retries are actually invoked when errors occur."""

    @pytest.mark.asyncio
    async def test_provider_retries_on_timeout(self):
        """Test that provider retries on timeout errors."""
        # Mock the retry.py module to avoid actual waiting
        with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
            # Create a test provider class that extends BaseMCPProvider
            with patch.multiple(
                "mcp_search_hub.providers.base_mcp.BaseMCPProvider",
                __init__=MagicMock(
                    return_value=None
                ),  # Skip BaseMCPProvider initialization
                __abstractmethods__=set(),  # Allow instantiation of abstract class
            ):
                # Create a test provider
                provider = BaseMCPProvider("test_provider")  # type: ignore
                provider.RETRY_ENABLED = True

                # Set up retry config
                provider.get_retry_config = lambda: RetryConfig(
                    max_retries=2, base_delay=0.01, jitter=False
                )

                # Track API call count
                call_count = 0

                # Mock the API function that would be retried
                async def api_function(query):
                    nonlocal call_count
                    call_count += 1
                    if call_count <= 2:
                        raise httpx.TimeoutException("API timeout")
                    return {"results": [{"title": query}]}

                # Use the provider's with_retry method
                retry_function = provider.with_retry(api_function)

                # Call the function with retry
                result = await retry_function("test query")

                # Verify it was called the expected number of times
                assert call_count == 3  # Initial + 2 retries
                assert result == {"results": [{"title": "test query"}]}

    @pytest.mark.asyncio
    async def test_provider_retries_on_connection_error(self):
        """Test that provider retries on connection errors."""
        # Mock the retry.py module to avoid actual waiting
        with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
            # Create a test provider class that extends BaseMCPProvider
            with patch.multiple(
                "mcp_search_hub.providers.base_mcp.BaseMCPProvider",
                __init__=MagicMock(return_value=None),
                __abstractmethods__=set(),
            ):
                # Create a test provider
                provider = BaseMCPProvider("test_provider")  # type: ignore
                provider.RETRY_ENABLED = True

                # Set up retry config
                provider.get_retry_config = lambda: RetryConfig(
                    max_retries=2, base_delay=0.01, jitter=False
                )

                # Track API call count
                call_count = 0

                # Mock the API function that would be retried
                async def api_function(query):
                    nonlocal call_count
                    call_count += 1
                    if call_count <= 2:
                        raise httpx.ConnectError("Connection refused")
                    return {"results": [{"title": query}]}

                # Use the provider's with_retry method
                retry_function = provider.with_retry(api_function)

                # Call the function with retry
                result = await retry_function("test query")

                # Verify it was called the expected number of times
                assert call_count == 3  # Initial + 2 retries
                assert result == {"results": [{"title": "test query"}]}

    @pytest.mark.asyncio
    async def test_provider_retries_on_server_error(self):
        """Test that provider retries on server errors."""
        # Mock the retry.py module to avoid actual waiting
        with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
            # Create a test provider class that extends BaseMCPProvider
            with patch.multiple(
                "mcp_search_hub.providers.base_mcp.BaseMCPProvider",
                __init__=MagicMock(return_value=None),
                __abstractmethods__=set(),
            ):
                # Create a test provider
                provider = BaseMCPProvider("test_provider")  # type: ignore
                provider.RETRY_ENABLED = True

                # Set up retry config
                provider.get_retry_config = lambda: RetryConfig(
                    max_retries=2, base_delay=0.01, jitter=False
                )

                # Track API call count
                call_count = 0

                # Mock the API function that would be retried
                async def api_function(query):
                    nonlocal call_count
                    call_count += 1
                    if call_count <= 2:
                        response = MagicMock()
                        response.status_code = 500
                        raise httpx.HTTPStatusError(
                            "Internal Server Error",
                            request=MagicMock(),
                            response=response,
                        )
                    return {"results": [{"title": query}]}

                # Use the provider's with_retry method
                retry_function = provider.with_retry(api_function)

                # Call the function with retry
                result = await retry_function("test query")

                # Verify it was called the expected number of times
                assert call_count == 3  # Initial + 2 retries
                assert result == {"results": [{"title": "test query"}]}

    @pytest.mark.asyncio
    async def test_provider_retries_on_rate_limit(self):
        """Test that provider retries on rate limit (429) errors."""
        # Mock the retry.py module to avoid actual waiting
        with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
            # Create a test provider class that extends BaseMCPProvider
            with patch.multiple(
                "mcp_search_hub.providers.base_mcp.BaseMCPProvider",
                __init__=MagicMock(return_value=None),
                __abstractmethods__=set(),
            ):
                # Create a test provider
                provider = BaseMCPProvider("test_provider")  # type: ignore
                provider.RETRY_ENABLED = True

                # Set up retry config
                provider.get_retry_config = lambda: RetryConfig(
                    max_retries=2, base_delay=0.01, jitter=False
                )

                # Track API call count
                call_count = 0

                # Mock the API function that would be retried
                async def api_function(query):
                    nonlocal call_count
                    call_count += 1
                    if call_count <= 2:
                        response = MagicMock()
                        response.status_code = 429
                        response.headers = {"Retry-After": "1"}
                        raise httpx.HTTPStatusError(
                            "Too Many Requests",
                            request=MagicMock(),
                            response=response,
                        )
                    return {"results": [{"title": query}]}

                # Use the provider's with_retry method
                retry_function = provider.with_retry(api_function)

                # Call the function with retry
                result = await retry_function("test query")

                # Verify it was called the expected number of times
                assert call_count == 3  # Initial + 2 retries
                assert result == {"results": [{"title": "test query"}]}

    @pytest.mark.asyncio
    async def test_provider_no_retry_on_client_error(self):
        """Test that provider doesn't retry on client errors (4xx except 429)."""
        # Mock the retry.py module to avoid actual waiting
        with patch("mcp_search_hub.utils.retry.asyncio.sleep", return_value=None):
            # Create a test provider class that extends BaseMCPProvider
            with patch.multiple(
                "mcp_search_hub.providers.base_mcp.BaseMCPProvider",
                __init__=MagicMock(return_value=None),
                __abstractmethods__=set(),
            ):
                # Create a test provider
                provider = BaseMCPProvider("test_provider")  # type: ignore
                provider.RETRY_ENABLED = True

                # Set up retry config
                provider.get_retry_config = lambda: RetryConfig(
                    max_retries=2, base_delay=0.01, jitter=False
                )

                # Track API call count
                call_count = 0

                # Mock the API function that would be retried
                async def api_function(query):
                    nonlocal call_count
                    call_count += 1
                    # Raise a non-retryable error (400)
                    response = MagicMock()
                    response.status_code = 400
                    raise httpx.HTTPStatusError(
                        "Bad Request", request=MagicMock(), response=response
                    )

                # Use the provider's with_retry method
                retry_function = provider.with_retry(api_function)

                # Call the function with retry
                with pytest.raises(httpx.HTTPStatusError):
                    await retry_function("test query")

                # Verify it was only called once (no retries)
                assert call_count == 1


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

            # Set up provider with mocked search method
            mock_provider = MagicMock()
            mock_provider.search = mock_search
            mock_generic.return_value = mock_provider

            # Create provider with the required configuration
            provider = ExaMCPProvider(api_key="test_key")

            # Override retry_enabled and config for testing
            provider.RETRY_ENABLED = True
            provider._retry_config = RetryConfig(max_retries=3, base_delay=0.01)

            # Ensure with_retry calls the original with our mock
            original_with_retry = BaseMCPProvider.with_retry
            provider.with_retry = lambda f: original_with_retry.__get__(provider)(f)

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

            class MockMixedExceptionProvider(BaseMCPProvider):
                def __init__(self):
                    self.call_count = 0
                    self.name = "mock_provider"
                    self.api_key = "test_key"
                    self.enabled = True

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
