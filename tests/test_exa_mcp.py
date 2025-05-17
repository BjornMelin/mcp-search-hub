"""Tests for Exa MCP provider integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.providers.exa_mcp import ExaMCPProvider


class TestExaMCPProvider:
    """Test Exa MCP provider functionality."""

    @pytest.fixture
    def provider(self):
        """Create an Exa MCP provider instance."""
        return ExaMCPProvider(api_key="test-api-key")

    def test_init(self, provider):
        """Test provider initialization."""
        assert provider.name == "exa"
        assert provider.tool_name == "web_search_exa"

    @pytest.mark.asyncio
    @patch("subprocess.run")
    async def test_initialize_success(self, mock_run, provider):
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

            await provider.initialize()

            assert provider.session == mock_session
            assert provider.initialized

    @pytest.mark.asyncio
    async def test_search_success(self, provider):
        """Test successful search."""
        provider.initialized = True
        provider.session = MagicMock()

        # Mock tool invocation
        mock_result = MagicMock()
        mock_result.content = [
            MagicMock(text={
                "results": [
                    {
                        "title": "Test Result",
                        "url": "https://example.com",
                        "snippet": "Test snippet",
                        "score": 0.9
                    }
                ]
            })
        ]
        provider.session.call_tool = AsyncMock(return_value=mock_result)

        query = SearchQuery(query="test query", max_results=5)
        results = await provider.search(query)

        assert len(results) == 1
        assert results[0].title == "Test Result"
        assert results[0].url == "https://example.com"
        assert results[0].snippet == "Test snippet"
        assert results[0].score == 0.9

    @pytest.mark.asyncio
    async def test_search_with_advanced_query(self, provider):
        """Test search with advanced query options."""
        provider.initialized = True
        provider.session = MagicMock()

        # Mock tool invocation
        mock_result = MagicMock()
        mock_result.content = [
            MagicMock(text={
                "results": [
                    {
                        "title": "Advanced Result",
                        "url": "https://example.com/advanced",
                        "snippet": "Advanced snippet",
                        "score": 0.95
                    }
                ]
            })
        ]
        provider.session.call_tool = AsyncMock(return_value=mock_result)

        query = SearchQuery(
            query="test query",
            max_results=5,
            advanced={
                "highlights": True,
                "startPublishedDate": "2023-01-01",
                "contents": "text"
            }
        )
        
        results = await provider.search(query)

        assert len(results) == 1
        assert results[0].title == "Advanced Result"

        # Verify the tool was called with correct parameters
        call_args = provider.session.call_tool.call_args
        assert call_args[0][0] == "web_search_exa"
        params = call_args[1]["arguments"]
        assert params["highlights"] is True
        assert params["startPublishedDate"] == "2023-01-01"
        assert params["contents"] == "text"

    @pytest.mark.asyncio
    async def test_search_not_initialized(self, provider):
        """Test search when not initialized."""
        provider.initialized = False

        query = SearchQuery(query="test query")
        with pytest.raises(RuntimeError, match="Provider not initialized"):
            await provider.search(query)

    @pytest.mark.asyncio
    async def test_search_error(self, provider):
        """Test search error handling."""
        provider.initialized = True
        provider.session = MagicMock()
        provider.session.call_tool = AsyncMock(
            side_effect=Exception("API error")
        )

        query = SearchQuery(query="test query")
        results = await provider.search(query)

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test cleanup."""
        provider.initialized = True
        provider.session = MagicMock()
        provider.process = MagicMock()
        provider.process.terminate = MagicMock()
        provider.process.wait = AsyncMock()

        await provider.close()

        provider.process.terminate.assert_called_once()
        assert not provider.initialized