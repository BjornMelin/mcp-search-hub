"""
Test suite for Linkup MCP provider integration.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.providers.linkup_mcp import LinkupMCPProvider, LinkupProvider
from mcp_search_hub.utils.errors import ProviderError


class TestLinkupMCPProvider:
    """Tests for LinkupMCPProvider."""

    @pytest_asyncio.fixture
    async def provider(self):
        """Create a LinkupMCPProvider instance."""
        provider = LinkupMCPProvider(api_key="test_key")
        yield provider
        # Cleanup
        if provider.session:
            await provider.close()

    def test_init(self):
        """Test provider initialization."""
        provider = LinkupMCPProvider(api_key="test_key")
        assert provider.api_key == "test_key"
        assert provider.session is None
        assert provider.server_params.command == sys.executable
        assert "-m" in provider.server_params.args
        assert "mcp_search_linkup" in provider.server_params.args

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
                "mcp_search_hub.providers.linkup_mcp.stdio_client"
            ) as mock_stdio:
                # Mock the stdio streams and session
                mock_read_stream = MagicMock()
                mock_write_stream = MagicMock()

                async def mock_stdio_client(*args, **kwargs):
                    return (mock_read_stream, mock_write_stream)

                mock_stdio.side_effect = mock_stdio_client

                mock_session = AsyncMock()
                mock_session.get_server_info.return_value = {
                    "name": "mcp-search-linkup"
                }

                with patch(
                    "mcp_search_hub.providers.linkup_mcp.ClientSession"
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
                    "mcp_search_hub.providers.linkup_mcp.stdio_client"
                ) as mock_stdio:
                    # Mock the stdio streams and session
                    mock_read_stream = MagicMock()
                    mock_write_stream = MagicMock()

                    async def mock_stdio_client(*args, **kwargs):
                        return (mock_read_stream, mock_write_stream)

                    mock_stdio.side_effect = mock_stdio_client

                    mock_session = AsyncMock()
                    mock_session.get_server_info.return_value = {
                        "name": "mcp-search-linkup"
                    }

                    with patch(
                        "mcp_search_hub.providers.linkup_mcp.ClientSession"
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
        provider.session.call_tool.return_value = [
            MagicMock(
                text='[{"title": "Result", "url": "https://example.com", "content": "Test content"}]'
            )
        ]

        result = await provider.call_tool(
            "search-web", {"query": "test", "depth": "standard"}
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_call_tool_error(self, provider):
        """Test tool calling error."""
        provider.session = AsyncMock()
        provider.session.call_tool.side_effect = Exception("Tool error")

        with pytest.raises(ProviderError):
            await provider.call_tool(
                "search-web", {"query": "test", "depth": "standard"}
            )

    @pytest.mark.asyncio
    async def test_list_tools_success(self, provider):
        """Test successful tools listing."""
        provider.session = AsyncMock()
        mock_tool = MagicMock()
        mock_tool.model_dump.return_value = {
            "name": "search-web",
            "description": "Web search tool",
        }
        provider.session.list_tools.return_value = [mock_tool]

        tools = await provider.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "search-web"

    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test closing connection."""
        mock_session = MagicMock()
        provider.session = mock_session

        await provider.close()
        assert provider.session is None


class TestLinkupProvider:
    """Tests for LinkupProvider."""

    @pytest_asyncio.fixture
    async def provider(self):
        """Create a LinkupProvider instance."""
        provider = LinkupProvider({"linkup_api_key": "test_key"})
        yield provider
        # Cleanup
        if provider._initialized:
            await provider.cleanup()

    def test_init(self):
        """Test provider initialization."""
        provider = LinkupProvider({"linkup_api_key": "test_key"})
        assert provider.api_key == "test_key"
        assert provider._initialized is False
        assert isinstance(provider.mcp_wrapper, LinkupMCPProvider)

    @pytest.mark.asyncio
    async def test_ensure_initialized(self, provider):
        """Test ensuring provider is initialized."""
        with patch.object(provider.mcp_wrapper, "initialize") as mock_init:
            await provider._ensure_initialized()
            mock_init.assert_called_once()
            assert provider._initialized is True

    @pytest.mark.asyncio
    async def test_search_success_list_result(self, provider):
        """Test successful search operation with list results."""
        query = SearchQuery(query="test query", max_results=5)

        # Mock the MCP wrapper response
        mock_result = [
            MagicMock(
                text='[{"title": "Test Result 1", "url": "https://example.com/1", "content": "Test content 1"}, {"title": "Test Result 2", "url": "https://example.com/2", "content": "Test content 2"}]'
            )
        ]

        with (
            patch.object(provider, "_ensure_initialized"),
            patch.object(
                provider.mcp_wrapper, "call_tool", return_value=mock_result
            ) as mock_call,
        ):
            result = await provider.search(query)

            assert len(result.results) == 2
            assert result.results[0].title == "Test Result 1"
            assert result.results[0].url == "https://example.com/1"
            assert result.results[0].source == "linkup"
            assert result.provider == "linkup"
            assert result.total_results == 2

            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_success_text_result(self, provider):
        """Test successful search with text result."""
        query = SearchQuery(query="test query", max_results=5)

        # Mock the MCP wrapper response with plain text
        mock_result = [MagicMock(text="Some search result content")]

        with (
            patch.object(provider, "_ensure_initialized"),
            patch.object(provider.mcp_wrapper, "call_tool", return_value=mock_result),
        ):
            result = await provider.search(query)

            assert len(result.results) == 1
            assert "Linkup Search" in result.results[0].title
            assert result.results[0].snippet == "Some search result content"

    @pytest.mark.asyncio
    async def test_search_with_raw_content(self, provider):
        """Test search with raw content enabled."""
        query = SearchQuery(query="test query", max_results=5, raw_content=True)

        # Mock the MCP wrapper response
        mock_result = [
            MagicMock(
                text='[{"title": "Result", "url": "https://example.com", "content": "Full content here"}]'
            )
        ]

        with (
            patch.object(provider, "_ensure_initialized"),
            patch.object(provider.mcp_wrapper, "call_tool", return_value=mock_result),
        ):
            result = await provider.search(query)

            assert len(result.results) == 1
            assert result.results[0].raw_content == "Full content here"

    @pytest.mark.asyncio
    async def test_search_error(self, provider):
        """Test search error handling."""
        query = SearchQuery(query="test query")

        with (
            patch.object(provider, "_ensure_initialized"),
            patch.object(
                provider.mcp_wrapper,
                "call_tool",
                side_effect=Exception("Search failed"),
            ),
        ):
            result = await provider.search(query)

            assert len(result.results) == 0
            assert result.error == "Search failed"

    def test_get_capabilities(self, provider):
        """Test getting provider capabilities."""
        capabilities = provider.get_capabilities()

        assert "content_types" in capabilities
        assert "news" in capabilities["content_types"]
        assert "current_events" in capabilities["content_types"]
        assert "premium_content" in capabilities["content_types"]
        assert capabilities["features"]["real_time"] is True
        assert capabilities["features"]["premium_sources"] is True
        assert capabilities["features"]["deep_search"] is True

    def test_estimate_cost(self, provider):
        """Test cost estimation."""
        basic_query = SearchQuery(query="test", advanced=False)
        advanced_query = SearchQuery(query="test", advanced=True)

        basic_cost = provider.estimate_cost(basic_query)
        advanced_cost = provider.estimate_cost(advanced_query)

        assert basic_cost == 0.005
        assert advanced_cost == 0.01

    @pytest.mark.asyncio
    async def test_check_status_success(self, provider):
        """Test successful status check."""
        with (
            patch.object(provider, "_ensure_initialized"),
            patch.object(
                provider.mcp_wrapper,
                "list_tools",
                return_value=[{"name": "search-web"}],
            ),
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
