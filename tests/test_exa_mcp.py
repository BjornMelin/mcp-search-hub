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
    @patch("mcp_search_hub.providers.base_mcp.stdio_client")
    @patch("asyncio.create_subprocess_exec")
    @patch("mcp.ClientSession")
    async def test_initialize_success(
        self, mock_client_session, mock_subprocess, mock_stdio_client, provider
    ):
        """Test successful initialization."""
        # Mock subprocess for installation check
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_subprocess.return_value = mock_process

        # Mock stdio_client streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Create async context manager for stdio_client
        async def async_context_manager():
            return mock_read_stream, mock_write_stream

        mock_stdio_client.return_value.__aenter__ = async_context_manager
        mock_stdio_client.return_value.__aexit__ = AsyncMock()

        # Mock MCP client
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session.list_tools = AsyncMock(
            return_value=[MagicMock(name="web_search_exa")]
        )
        mock_client_session.return_value = mock_session

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

    @pytest.mark.asyncio
    async def test_search_with_advanced_query(self, provider):
        """Test search with advanced query options."""
        provider.initialized = True
        provider.session = MagicMock()

        # Mock tool invocation
        mock_result = MagicMock()
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

        query = SearchQuery(
            query="test query",
            max_results=5,
            advanced={
                "highlights": True,
                "startPublishedDate": "2023-01-01",
                "contents": "text",
            },
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
        provider.session.call_tool = AsyncMock(side_effect=Exception("API error"))

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
