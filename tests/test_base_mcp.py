"""Base test class for MCP providers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_search_hub.models.query import SearchQuery


class BaseMCPProviderTestMixin:
    """Base test mixin for all MCP providers. Provides common test cases."""

    provider_class = None  # To be set by subclasses
    provider_name = None  # To be set by subclasses
    tool_name = None  # To be set by subclasses

    def get_provider(self, api_key="test_key"):
        """Get an instance of the provider."""
        if not self.provider_class:
            raise NotImplementedError("Subclasses must set provider_class")
        return self.provider_class(api_key=api_key)

    def test_init(self):
        """Test provider initialization."""
        provider = self.get_provider()
        assert provider.name == self.provider_name

    @patch("subprocess.run")
    async def test_initialize_success(self, mock_run):
        """Test successful initialization."""
        # Mock subprocess for installation check
        mock_run.return_value = MagicMock(returncode=0)

        # Mock MCP client
        with patch("mcp.ClientSession.create") as mock_create:
            mock_session = MagicMock()
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_session
            mock_create.return_value = mock_context

            # Mock initialization
            mock_session.initialize = AsyncMock()

            provider = self.get_provider()
            await provider.initialize()

            assert provider.session == mock_session
            assert provider.initialized

    async def test_search_success(self):
        """Test successful search."""
        provider = self.get_provider()
        provider.initialized = True
        provider.session = MagicMock()

        # Mock tool invocation
        mock_result = AsyncMock()
        mock_result.content = [
            MagicMock(
                text={
                    "results": [
                        {
                            "title": "Test Result",
                            "url": "https://example.com",
                            "snippet": "Test snippet",
                            "score": 0.9,
                        }
                    ]
                }
            )
        ]
        provider.session.call_tool = AsyncMock(return_value=mock_result)

        query = SearchQuery(query="test query", max_results=5)
        results = await provider.search(query)

        assert len(results) == 1
        assert results[0].title == "Test Result"
        assert results[0].url == "https://example.com"
        assert results[0].snippet == "Test snippet"
        assert results[0].score == 0.9

    async def test_search_not_initialized(self):
        """Test search when not initialized."""
        provider = self.get_provider()
        provider.initialized = False

        query = SearchQuery(query="test query")
        with pytest.raises(RuntimeError, match="Provider not initialized"):
            await provider.search(query)

    async def test_search_error(self):
        """Test search error handling."""
        provider = self.get_provider()
        provider.initialized = True
        provider.session = MagicMock()
        provider.session.call_tool = AsyncMock(side_effect=Exception("API error"))

        query = SearchQuery(query="test query")
        results = await provider.search(query)

        assert len(results) == 0

    async def test_close(self):
        """Test cleanup."""
        provider = self.get_provider()
        provider.initialized = True
        provider.session = MagicMock()
        provider.process = MagicMock()
        provider.process.terminate = MagicMock()
        provider.process.wait = AsyncMock()

        await provider.close()

        provider.process.terminate.assert_called_once()
        assert not provider.initialized


class AdvancedQueryTestMixin:
    """Mixin for providers that support advanced queries."""

    async def test_search_with_advanced_query(self):
        """Test search with advanced query options."""
        provider = self.get_provider()
        provider.initialized = True
        provider.session = MagicMock()

        # Mock tool invocation
        mock_result = AsyncMock()
        mock_result.content = [
            MagicMock(
                text={
                    "results": [
                        {
                            "title": "Advanced Result",
                            "url": "https://example.com/advanced",
                            "snippet": "Advanced snippet",
                            "score": 0.95,
                        }
                    ]
                }
            )
        ]
        provider.session.call_tool = AsyncMock(return_value=mock_result)

        # Test with provider-specific advanced options
        advanced_options = self.get_advanced_options()
        query = SearchQuery(
            query="test query", max_results=5, advanced=advanced_options
        )

        results = await provider.search(query)

        # Verify results
        assert len(results) == 1
        assert results[0].title == "Advanced Result"

        # Verify the tool was called with correct parameters
        call_args = provider.session.call_tool.call_args
        assert call_args[0][0] == self.tool_name

        # Provider-specific verification
        self.verify_advanced_params(call_args[1]["arguments"])

    def get_advanced_options(self):
        """Get provider-specific advanced options. Override in subclasses."""
        return {}

    def verify_advanced_params(self, params):
        """Verify provider-specific advanced parameters. Override in subclasses."""


class RawContentTestMixin:
    """Mixin for providers that support raw content extraction."""

    async def test_search_with_raw_content(self):
        """Test search with raw content extraction."""
        provider = self.get_provider()
        provider.initialized = True
        provider.session = MagicMock()

        # Mock tool invocation with raw content
        mock_result = AsyncMock()
        mock_result.content = [
            MagicMock(
                text={
                    "results": [
                        {
                            "title": "Content Result",
                            "url": "https://example.com/content",
                            "snippet": "Content snippet",
                            "content": "This is the full raw content",
                            "score": 0.88,
                        }
                    ]
                }
            )
        ]
        provider.session.call_tool = AsyncMock(return_value=mock_result)

        query = SearchQuery(query="test query", max_results=5, raw_content=True)

        results = await provider.search(query)

        assert len(results) == 1
        assert results[0].title == "Content Result"
        assert results[0].raw_content == "This is the full raw content"

        # Verify the tool was called with raw content flag
        call_args = provider.session.call_tool.call_args
        params = call_args[1]["arguments"]
        self.verify_raw_content_params(params)

    def verify_raw_content_params(self, params):
        """Verify provider-specific raw content parameters. Override in subclasses."""
