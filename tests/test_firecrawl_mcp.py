"""Tests for Firecrawl MCP provider integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.providers.firecrawl_mcp import (
    FirecrawlMCPProvider,
    FirecrawlProvider,
)
from mcp_search_hub.utils.errors import ProviderError


@pytest.fixture
def firecrawl_mcp_provider():
    """Create a Firecrawl MCP provider instance."""
    return FirecrawlMCPProvider(api_key="test-api-key")


@pytest.fixture
def firecrawl_provider():
    """Create a Firecrawl provider instance."""
    return FirecrawlProvider(api_key="test-api-key")


class TestFirecrawlMCPProvider:
    """Test Firecrawl MCP provider functionality."""

    @pytest.mark.asyncio
    async def test_initialize_success(self, firecrawl_mcp_provider):
        """Test successful initialization."""
        with (
            patch("subprocess.run") as mock_run,
            patch("mcp_search_hub.providers.firecrawl_mcp.stdio_client") as mock_client,
        ):
            # Mock version check success
            mock_run.return_value = MagicMock(returncode=0)

            # Mock client connection
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            # stdio_client is an async function that should return a tuple
            mock_client.side_effect = AsyncMock(return_value=(mock_read, mock_write))

            # Mock session
            mock_session = AsyncMock()
            mock_session.get_server_info = AsyncMock(
                return_value={"name": "firecrawl-mcp"}
            )

            with patch(
                "mcp_search_hub.providers.firecrawl_mcp.ClientSession",
                return_value=mock_session,
            ):
                await firecrawl_mcp_provider.initialize()

                assert firecrawl_mcp_provider.session is not None

    @pytest.mark.asyncio
    async def test_initialize_install_required(self, firecrawl_mcp_provider):
        """Test initialization when installation is required."""
        with (
            patch("subprocess.run") as mock_run,
            patch("mcp_search_hub.providers.firecrawl_mcp.stdio_client") as mock_client,
        ):
            # Mock version check failure (not installed)
            check_result = MagicMock(returncode=1)
            install_result = MagicMock(returncode=0)
            mock_run.side_effect = [check_result, install_result]

            # Mock client connection
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            # stdio_client is an async function that should return a tuple
            mock_client.side_effect = AsyncMock(return_value=(mock_read, mock_write))

            # Mock session
            mock_session = AsyncMock()
            mock_session.get_server_info = AsyncMock(
                return_value={"name": "firecrawl-mcp"}
            )

            with patch(
                "mcp_search_hub.providers.firecrawl_mcp.ClientSession",
                return_value=mock_session,
            ):
                await firecrawl_mcp_provider.initialize()

                # Should have called npm install
                assert mock_run.call_count == 2
                assert "npm" in mock_run.call_args_list[1][0][0]

    @pytest.mark.asyncio
    async def test_initialize_install_failure(self, firecrawl_mcp_provider):
        """Test initialization when installation fails."""
        with patch("subprocess.run") as mock_run:
            # Mock version check failure
            check_result = MagicMock(returncode=1)
            install_result = MagicMock(returncode=1, stderr="Installation failed")
            mock_run.side_effect = [check_result, install_result]

            with pytest.raises(
                ProviderError, match="Failed to install Firecrawl MCP server"
            ):
                await firecrawl_mcp_provider.initialize()

    @pytest.mark.asyncio
    async def test_call_tool(self, firecrawl_mcp_provider):
        """Test calling a tool."""
        # Mock session
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value={"result": "success"})
        firecrawl_mcp_provider.session = mock_session

        result = await firecrawl_mcp_provider.call_tool("test_tool", {"param": "value"})

        assert result["result"] == "success"
        mock_session.call_tool.assert_called_once_with(
            "test_tool", arguments={"param": "value"}
        )

    @pytest.mark.asyncio
    async def test_list_tools(self, firecrawl_mcp_provider):
        """Test listing tools."""
        # Mock session
        mock_session = AsyncMock()
        mock_tool = MagicMock()
        mock_tool.model_dump = MagicMock(return_value={"name": "test_tool"})
        mock_session.list_tools = AsyncMock(return_value=[mock_tool])
        firecrawl_mcp_provider.session = mock_session

        tools = await firecrawl_mcp_provider.list_tools()

        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"


class TestFirecrawlProvider:
    """Test Firecrawl provider integration."""

    @pytest.mark.asyncio
    async def test_search_with_url(self, firecrawl_provider):
        """Test search with URL."""
        with patch.object(firecrawl_provider, "scrape_url") as mock_scrape:
            mock_scrape.return_value = [
                {
                    "title": "Test Page",
                    "url": "https://example.com",
                    "content": "Test content",
                }
            ]

            query = SearchQuery(query="https://example.com", max_results=10)
            response = await firecrawl_provider.search(query)

            assert len(response.results) == 1
            assert response.results[0].title == "Test Page"
            mock_scrape.assert_called_once_with("https://example.com", max_results=10)

    @pytest.mark.asyncio
    async def test_search_without_url(self, firecrawl_provider):
        """Test search without URL returns empty."""
        query = SearchQuery(query="test query", max_results=10)
        response = await firecrawl_provider.search(query)
        assert response.results == []

    @pytest.mark.asyncio
    async def test_scrape_url(self, firecrawl_provider):
        """Test URL scraping."""
        mock_response = {
            "title": "Test Page",
            "markdown": "# Test Page\n\nTest content",
            "metadata": {"author": "test"},
        }

        with patch.object(firecrawl_provider, "_ensure_initialized") as mock_init:
            with patch.object(firecrawl_provider.mcp_client, "call_tool") as mock_call:
                mock_call.return_value = mock_response

                results = await firecrawl_provider.scrape_url("https://example.com")

                assert len(results) == 1
                assert results[0]["title"] == "Test Page"
                assert results[0]["content"] == "# Test Page\n\nTest content"
                assert results[0]["metadata"]["author"] == "test"

    @pytest.mark.asyncio
    async def test_firecrawl_map(self, firecrawl_provider):
        """Test URL mapping."""
        mock_response = {
            "urls": ["https://example.com/page1", "https://example.com/page2"]
        }

        with patch.object(firecrawl_provider, "_ensure_initialized") as mock_init:
            with patch.object(firecrawl_provider.mcp_client, "call_tool") as mock_call:
                mock_call.return_value = mock_response

                result = await firecrawl_provider.firecrawl_map("https://example.com")

                assert result["urls"][0] == "https://example.com/page1"
                mock_call.assert_called_once_with(
                    "firecrawl_map", {"url": "https://example.com"}
                )

    @pytest.mark.asyncio
    async def test_get_available_tools(self, firecrawl_provider):
        """Test getting available tools."""
        mock_tools = [{"name": "firecrawl_scrape"}, {"name": "firecrawl_map"}]

        with patch.object(firecrawl_provider, "_ensure_initialized") as mock_init:
            with patch.object(firecrawl_provider.mcp_client, "list_tools") as mock_list:
                mock_list.return_value = mock_tools

                tools = await firecrawl_provider.get_available_tools()

                assert len(tools) == 2
                assert tools[0]["name"] == "firecrawl_scrape"
