"""
Test suite for Tavily MCP provider integration.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.providers.tavily_mcp import TavilyMCPProvider, TavilyProvider
from mcp_search_hub.utils.errors import ProviderError


class TestTavilyMCPProvider:
    """Tests for TavilyMCPProvider."""

    @pytest_asyncio.fixture
    async def provider(self):
        """Create a TavilyMCPProvider instance."""
        provider = TavilyMCPProvider(api_key="test_key")
        yield provider
        # Cleanup
        if provider.session:
            await provider.close()

    def test_init(self):
        """Test provider initialization."""
        provider = TavilyMCPProvider(api_key="test_key")
        assert provider.api_key == "test_key"
        assert provider.session is None
        assert provider.server_params.command == "npx"
        assert "-y" in provider.server_params.args
        assert "tavily-mcp@0.2.0" in provider.server_params.args
        assert provider.server_params.env["TAVILY_API_KEY"] == "test_key"

    @pytest.mark.asyncio
    async def test_check_installation_success(self, provider):
        """Test successful installation check."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = await provider._check_installation()
            assert result is True
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_installation_failure(self, provider):
        """Test failed installation check."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = await provider._check_installation()
            assert result is False

    @pytest.mark.asyncio
    async def test_install_server_success(self, provider):
        """Test successful server installation."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            await provider._install_server()
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_install_server_failure(self, provider):
        """Test failed server installation."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="Installation failed"
            )
            with pytest.raises(ProviderError):
                await provider._install_server()

    @pytest.mark.asyncio
    async def test_initialize_success(self, provider):
        """Test successful initialization."""
        with patch.object(provider, "_check_installation", return_value=True):
            with patch(
                "mcp_search_hub.providers.tavily_mcp.stdio_client"
            ) as mock_stdio:
                # Mock the stdio streams and session
                mock_read_stream = MagicMock()
                mock_write_stream = MagicMock()

                async def mock_stdio_client(*args, **kwargs):
                    return (mock_read_stream, mock_write_stream)

                mock_stdio.side_effect = mock_stdio_client

                mock_session = AsyncMock()
                mock_session.get_server_info.return_value = {"name": "tavily-mcp"}

                with patch(
                    "mcp_search_hub.providers.tavily_mcp.ClientSession"
                ) as mock_client_session:
                    mock_client_session.return_value.__aenter__.return_value = (
                        mock_session
                    )

                    await provider.initialize()
                    assert provider.session == mock_session

    @pytest.mark.asyncio
    async def test_initialize_with_installation(self, provider):
        """Test initialization with installation needed."""
        with patch.object(provider, "_check_installation", return_value=False):
            with patch.object(provider, "_install_server") as mock_install:
                with patch(
                    "mcp_search_hub.providers.tavily_mcp.stdio_client"
                ) as mock_stdio:
                    # Mock the stdio streams and session
                    mock_read_stream = MagicMock()
                    mock_write_stream = MagicMock()

                    async def mock_stdio_client(*args, **kwargs):
                        return (mock_read_stream, mock_write_stream)

                    mock_stdio.side_effect = mock_stdio_client

                    mock_session = AsyncMock()
                    mock_session.get_server_info.return_value = {"name": "tavily-mcp"}

                    with patch(
                        "mcp_search_hub.providers.tavily_mcp.ClientSession"
                    ) as mock_client_session:
                        mock_client_session.return_value.__aenter__.return_value = (
                            mock_session
                        )

                        await provider.initialize()
                        mock_install.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool_success(self, provider):
        """Test successful tool calling."""
        provider.session = AsyncMock()
        expected_result = {
            "content": [
                {
                    "type": "text",
                    "text": '{"results": [{"title": "Test Result", "url": "https://example.com", "content": "Test content"}]}',
                }
            ]
        }
        provider.session.call_tool.return_value = expected_result

        result = await provider.call_tool("tavily-search", {"query": "test"})
        assert result == expected_result
        provider.session.call_tool.assert_called_once_with(
            "tavily-search", arguments={"query": "test"}
        )

    @pytest.mark.asyncio
    async def test_call_tool_error(self, provider):
        """Test tool calling error."""
        provider.session = AsyncMock()
        provider.session.call_tool.side_effect = Exception("Tool error")

        with pytest.raises(ProviderError):
            await provider.call_tool("tavily-search", {"query": "test"})

    @pytest.mark.asyncio
    async def test_list_tools_success(self, provider):
        """Test successful tools listing."""
        provider.session = AsyncMock()
        mock_tool = MagicMock()
        mock_tool.model_dump.return_value = {
            "name": "tavily-search",
            "description": "Search tool",
        }
        provider.session.list_tools.return_value = [mock_tool]

        tools = await provider.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "tavily-search"

    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test closing connection."""
        mock_session = MagicMock()
        provider.session = mock_session

        await provider.close()
        assert provider.session is None


class TestTavilyProvider:
    """Tests for TavilyProvider."""

    @pytest_asyncio.fixture
    async def provider(self):
        """Create a TavilyProvider instance."""
        provider = TavilyProvider({"tavily_api_key": "test_key"})
        yield provider
        # Cleanup
        if provider._initialized:
            await provider.cleanup()

    def test_init(self):
        """Test provider initialization."""
        provider = TavilyProvider({"tavily_api_key": "test_key"})
        assert provider.api_key == "test_key"
        assert provider._initialized is False
        assert isinstance(provider.mcp_wrapper, TavilyMCPProvider)

    @pytest.mark.asyncio
    async def test_ensure_initialized(self, provider):
        """Test ensuring provider is initialized."""
        with patch.object(provider.mcp_wrapper, "initialize") as mock_init:
            await provider._ensure_initialized()
            mock_init.assert_called_once()
            assert provider._initialized is True

    @pytest.mark.asyncio
    async def test_search_success(self, provider):
        """Test successful search operation."""
        query = SearchQuery(query="test query", max_results=5)

        # Mock the MCP wrapper response
        mock_result = {
            "content": [
                {
                    "type": "text",
                    "text": '{"results": [{"title": "Test Result", "url": "https://example.com", "content": "Test content"}]}',
                }
            ]
        }

        with patch.object(provider, "_ensure_initialized"):
            with patch.object(
                provider.mcp_wrapper, "call_tool", return_value=mock_result
            ) as mock_call:
                result = await provider.search(query)

                assert len(result.results) == 1
                assert result.results[0].title == "Test Result"
                assert result.results[0].url == "https://example.com"
                assert result.results[0].source == "tavily"
                assert result.provider == "tavily"
                assert result.total_results == 1

                mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_advanced_query(self, provider):
        """Test search with advanced query."""
        query = SearchQuery(query="test query", max_results=5, advanced=True)

        # Mock the MCP wrapper response
        mock_result = {
            "content": [
                {
                    "type": "text",
                    "text": '{"results": [{"title": "Test Result", "url": "https://example.com", "content": "Test content"}]}',
                }
            ]
        }

        with patch.object(provider, "_ensure_initialized"):
            with patch.object(
                provider.mcp_wrapper, "call_tool", return_value=mock_result
            ) as mock_call:
                await provider.search(query)

                # Check that the search_depth was set to "advanced"
                call_args = mock_call.call_args[0][1]
                assert call_args["options"]["searchDepth"] == "advanced"

    @pytest.mark.asyncio
    async def test_search_with_raw_content(self, provider):
        """Test search with raw content enabled."""
        query = SearchQuery(query="test query", max_results=5, raw_content=True)

        # Mock the MCP wrapper response
        mock_result = {
            "content": [
                {
                    "type": "text",
                    "text": '{"results": [{"title": "Result", "url": "https://example.com", "content": "Content", "raw_content": "Full content here"}]}',
                }
            ]
        }

        with patch.object(provider, "_ensure_initialized"):
            with patch.object(
                provider.mcp_wrapper, "call_tool", return_value=mock_result
            ) as mock_call:
                result = await provider.search(query)

                assert len(result.results) == 1
                assert result.results[0].raw_content == "Full content here"

                # Check that includeRawContent was set to True
                call_args = mock_call.call_args[0][1]
                assert call_args["options"]["includeRawContent"] is True

    @pytest.mark.asyncio
    async def test_search_error(self, provider):
        """Test search error handling."""
        query = SearchQuery(query="test query")

        with patch.object(provider, "_ensure_initialized"):
            with patch.object(
                provider.mcp_wrapper,
                "call_tool",
                side_effect=Exception("Search failed"),
            ):
                result = await provider.search(query)

                assert len(result.results) == 0
                assert result.error == "Search failed"

    @pytest.mark.asyncio
    async def test_extract_content(self, provider):
        """Test extract content functionality."""
        url = "https://example.com"

        # Mock the MCP wrapper response
        mock_result = {
            "content": [{"type": "text", "text": "Extracted content from the webpage"}]
        }

        with patch.object(provider, "_ensure_initialized"):
            with patch.object(
                provider.mcp_wrapper, "call_tool", return_value=mock_result
            ) as mock_call:
                result = await provider.extract_content(url)

                assert result == mock_result
                mock_call.assert_called_once()

                # Check URL was passed correctly
                call_args = mock_call.call_args[0][1]
                assert call_args["urls"] == [url]
                assert call_args["options"]["extractDepth"] == "advanced"

    def test_get_capabilities(self, provider):
        """Test getting provider capabilities."""
        capabilities = provider.get_capabilities()

        assert "content_types" in capabilities
        assert "general" in capabilities["content_types"]
        assert "technical" in capabilities["content_types"]
        assert "news" in capabilities["content_types"]
        assert "academic" in capabilities["content_types"]
        assert capabilities["features"]["rag_optimized"] is True
        assert capabilities["features"]["content_extraction"] is True
        assert capabilities["features"]["advanced_search"] is True

    def test_estimate_cost(self, provider):
        """Test cost estimation."""
        basic_query = SearchQuery(query="test", advanced=False)
        advanced_query = SearchQuery(query="test", advanced=True)

        basic_cost = provider.estimate_cost(basic_query)
        advanced_cost = provider.estimate_cost(advanced_query)

        assert basic_cost == 0.01
        assert advanced_cost == 0.02

    @pytest.mark.asyncio
    async def test_check_status_success(self, provider):
        """Test successful status check."""
        with patch.object(provider, "_ensure_initialized"):
            with patch.object(
                provider.mcp_wrapper,
                "list_tools",
                return_value=[{"name": "tavily-search"}],
            ):
                status, message = await provider.check_status()

                assert status.value == "ok"
                assert "operational" in message

    @pytest.mark.asyncio
    async def test_check_status_failure(self, provider):
        """Test failed status check."""
        with patch.object(
            provider, "_ensure_initialized", side_effect=Exception("Connection failed")
        ):
            status, message = await provider.check_status()

            assert status.value == "failed"
            assert "Connection failed" in message

    @pytest.mark.asyncio
    async def test_cleanup(self, provider):
        """Test cleanup method."""
        provider._initialized = True

        with patch.object(provider.mcp_wrapper, "close") as mock_close:
            await provider.cleanup()
            mock_close.assert_called_once()
            assert provider._initialized is False
