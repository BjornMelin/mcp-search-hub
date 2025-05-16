"""
Test suite for Tavily MCP provider integration.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.providers.tavily_mcp import TavilyMCPProvider


class TestTavilyMCPProvider:
    """Tests for TavilyMCPProvider."""

    @pytest_asyncio.fixture
    async def provider(self):
        """Create a TavilyMCPProvider instance."""
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test_key"}, clear=False):
            provider = TavilyMCPProvider(api_key="test_key")
            yield provider

    def test_init(self):
        """Test provider initialization."""
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test_key"}, clear=False):
            provider = TavilyMCPProvider(api_key="test_key")
            assert provider.api_key == "test_key"
            assert provider.session is None
            assert provider.server_params.command == "npx"
            assert "tavily-mcp@0.2.0" in provider.server_params.args
            assert provider.server_params.env["TAVILY_API_KEY"] == "test_key"

    @pytest.mark.asyncio
    async def test_initialize_success(self, provider):
        """Test successful initialization."""
        with (
            patch(
                "mcp_search_hub.providers.base_mcp.asyncio.create_subprocess_exec"
            ) as mock_create_subprocess,
            patch(
                "mcp_search_hub.providers.base_mcp.asyncio.wait_for",
                new_callable=AsyncMock,
            ) as mock_wait_for,
            patch(
                "mcp_search_hub.providers.base_mcp.stdio_client", new_callable=AsyncMock
            ) as mock_client,
            patch(
                "mcp_search_hub.providers.base_mcp.ClientSession"
            ) as mock_session_class,
        ):
            # Mock subprocess for both installation check and server launch
            mock_check_process = AsyncMock()
            mock_check_process.returncode = 0
            mock_check_process.communicate.return_value = (b"", b"")

            mock_server_process = AsyncMock()
            mock_server_process.communicate.return_value = (b"", b"")

            # First call returns the check process (installation check), second returns server process
            mock_create_subprocess.side_effect = [
                mock_check_process,
                mock_server_process,
            ]

            # Mock wait_for to just return the process.communicate result
            mock_wait_for.return_value = (b"", b"")

            # Mock client
            mock_client.return_value = (AsyncMock(), AsyncMock())

            # Mock session
            mock_session = AsyncMock()
            # Mock the tool list response
            mock_tool = MagicMock()
            mock_tool.name = "tavily_search"
            mock_session.list_tools.return_value = [mock_tool]
            mock_session_class.return_value = mock_session

            await provider.initialize()

            assert provider.session == mock_session
            mock_session.list_tools.assert_called_once()
            # Check that subprocess was called at least once
            assert mock_create_subprocess.call_count >= 1

    @pytest.mark.asyncio
    async def test_search_success(self, provider):
        """Test successful search operation."""
        query = SearchQuery(query="test query", max_results=5)

        # Mock the session response
        mock_result = MagicMock()
        mock_content = MagicMock()
        mock_content.text = {
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com",
                    "snippet": "Test snippet",
                    "content": "Test content",
                }
            ]
        }
        mock_result.content = [mock_content]

        provider.session = AsyncMock()
        provider.session.call_tool.return_value = mock_result

        result = await provider.search(query)

        assert len(result.results) == 1
        assert result.results[0].title == "Test Result"
        assert result.results[0].url == "https://example.com"
        assert result.results[0].source == "tavily"
        assert result.provider == "tavily"
        assert result.total_results == 1

        provider.session.call_tool.assert_called_once_with(
            "tavily_search",
            {
                "query": "test query",
                "max_results": 5,
                "search_depth": "basic",
                "include_raw_content": False,
            },
        )

    @pytest.mark.asyncio
    async def test_search_with_advanced_query(self, provider):
        """Test search with advanced query."""
        # Prepare advanced query with dict options
        options = {"deep_search": True}
        query = SearchQuery(query="test query", max_results=5)
        query.advanced = options

        # Mock the session response
        mock_result = MagicMock()
        mock_content = MagicMock()
        mock_content.text = {"results": []}
        mock_result.content = [mock_content]

        provider.session = AsyncMock()
        provider.session.call_tool.return_value = mock_result

        await provider.search(query)

        # Check that search_depth was set to "advanced"
        call_args = provider.session.call_tool.call_args[0][1]
        assert call_args["search_depth"] == "advanced"

    @pytest.mark.asyncio
    async def test_search_with_raw_content(self, provider):
        """Test search with raw content enabled."""
        query = SearchQuery(query="test query", max_results=5, raw_content=True)

        # Mock the session response
        mock_result = MagicMock()
        mock_content = MagicMock()
        mock_content.text = {
            "results": [
                {
                    "title": "Result",
                    "url": "https://example.com",
                    "content": "Content",
                    "raw_content": "Full content here",
                }
            ]
        }
        mock_result.content = [mock_content]

        provider.session = AsyncMock()
        provider.session.call_tool.return_value = mock_result

        result = await provider.search(query)

        assert len(result.results) == 1
        assert result.results[0].raw_content == "Full content here"

        # Check that include_raw_content was set to True
        call_args = provider.session.call_tool.call_args[0][1]
        assert call_args["include_raw_content"] is True

    @pytest.mark.asyncio
    async def test_search_error(self, provider):
        """Test search error handling."""
        query = SearchQuery(query="test query")

        provider.session = AsyncMock()
        provider.session.call_tool.side_effect = Exception("Search failed")

        result = await provider.search(query)

        assert len(result.results) == 0
        assert result.error == "Search failed: Search failed"

    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test closing connection."""
        provider.session = AsyncMock()

        await provider._cleanup()
        assert provider.session is None
