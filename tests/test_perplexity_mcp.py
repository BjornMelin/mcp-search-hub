"""
Test suite for Perplexity MCP provider integration.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.providers.perplexity_mcp import (
    PerplexityMCPProvider,
    PerplexityProvider,
)
from mcp_search_hub.utils.errors import ProviderError


class TestPerplexityMCPProvider:
    """Tests for PerplexityMCPProvider."""

    @pytest_asyncio.fixture
    async def provider(self):
        """Create an PerplexityMCPProvider instance."""
        provider = PerplexityMCPProvider(api_key="test_key")
        yield provider
        # Cleanup
        if provider.session:
            await provider.close()

    def test_init(self):
        """Test provider initialization."""
        provider = PerplexityMCPProvider(api_key="test_key")
        assert provider.api_key == "test_key"
        assert provider.session is None
        assert provider.server_params.command == "npx"
        assert "perplexity-mcp" in provider.server_params.args

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
                "mcp_search_hub.providers.perplexity_mcp.stdio_client"
            ) as mock_stdio:
                # Mock the stdio streams and session
                mock_read_stream = MagicMock()
                mock_write_stream = MagicMock()

                async def mock_stdio_client(*args, **kwargs):
                    return (mock_read_stream, mock_write_stream)

                mock_stdio.side_effect = mock_stdio_client

                mock_session = AsyncMock()
                mock_session.get_server_info.return_value = {"name": "perplexity-mcp"}

                with patch(
                    "mcp_search_hub.providers.perplexity_mcp.ClientSession"
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
                    "mcp_search_hub.providers.perplexity_mcp.stdio_client"
                ) as mock_stdio:
                    # Mock the stdio streams and session
                    mock_read_stream = MagicMock()
                    mock_write_stream = MagicMock()

                    async def mock_stdio_client(*args, **kwargs):
                        return (mock_read_stream, mock_write_stream)

                    mock_stdio.side_effect = mock_stdio_client

                    mock_session = AsyncMock()
                    mock_session.get_server_info.return_value = {
                        "name": "perplexity-mcp"
                    }

                    with patch(
                        "mcp_search_hub.providers.perplexity_mcp.ClientSession"
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
        provider.session.call_tool.return_value = {"result": "success"}

        result = await provider.call_tool(
            "perplexity_ask", {"messages": [{"role": "user", "content": "test"}]}
        )
        assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_call_tool_error(self, provider):
        """Test tool calling error."""
        provider.session = AsyncMock()
        provider.session.call_tool.side_effect = Exception("Tool error")

        with pytest.raises(ProviderError):
            await provider.call_tool(
                "perplexity_ask", {"messages": [{"role": "user", "content": "test"}]}
            )

    @pytest.mark.asyncio
    async def test_list_tools_success(self, provider):
        """Test successful tools listing."""
        provider.session = AsyncMock()
        mock_tool = MagicMock()
        mock_tool.model_dump.return_value = {
            "name": "perplexity_ask",
            "description": "Test tool",
        }
        provider.session.list_tools.return_value = [mock_tool]

        tools = await provider.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "perplexity_ask"

    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test closing connection."""
        mock_session = MagicMock()
        provider.session = mock_session

        await provider.close()
        assert provider.session is None


class TestPerplexityProvider:
    """Tests for PerplexityProvider."""

    @pytest_asyncio.fixture
    async def provider(self):
        """Create an PerplexityProvider instance."""
        provider = PerplexityProvider({"perplexity_api_key": "test_key"})
        yield provider
        # Cleanup
        if provider._initialized:
            await provider.cleanup()

    def test_init(self):
        """Test provider initialization."""
        provider = PerplexityProvider({"perplexity_api_key": "test_key"})
        assert provider.api_key == "test_key"
        assert provider._initialized is False
        assert isinstance(provider.mcp_wrapper, PerplexityMCPProvider)

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
        mock_response = {
            "sources": [
                {
                    "title": "Test Result 1",
                    "url": "https://example.com/1",
                    "snippet": "Test snippet 1",
                    "domain": "example.com",
                },
                {
                    "title": "Test Result 2",
                    "url": "https://example.com/2",
                    "snippet": "Test snippet 2",
                    "domain": "example.com",
                },
            ],
            "content": "Test answer content",
            "citations": ["1", "2"],
        }

        with (
            patch.object(provider, "_ensure_initialized"),
            patch.object(
                provider.mcp_wrapper, "call_tool", return_value=mock_response
            ) as mock_call,
        ):
            result = await provider.search(query)

            assert len(result.results) == 2
            assert result.results[0].title == "Test Result 1"
            assert result.results[0].url == "https://example.com/1"
            assert result.results[0].source == "perplexity"
            assert result.provider == "perplexity"
            assert result.total_results == 2

            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_content_only(self, provider):
        """Test search with content but no sources."""
        query = SearchQuery(query="test query", max_results=5, raw_content=True)

        # Mock response with only content
        mock_response = {
            "content": "Test answer content",
            "citations": ["1", "2"],
        }

        with (
            patch.object(provider, "_ensure_initialized"),
            patch.object(provider.mcp_wrapper, "call_tool", return_value=mock_response),
        ):
            result = await provider.search(query)

            assert len(result.results) == 1
            assert "Perplexity Answer" in result.results[0].title
            # Note: SearchResult doesn't have a content attribute, it uses snippet
            assert result.results[0].snippet == "Test answer content"

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

    @pytest.mark.asyncio
    async def test_perplexity_research(self, provider):
        """Test perplexity research method."""
        with (
            patch.object(provider, "_ensure_initialized"),
            patch.object(
                provider.mcp_wrapper, "call_tool", return_value={"result": "research"}
            ) as mock_call,
        ):
            result = await provider.perplexity_research("test topic")

            assert result == {"result": "research"}
            mock_call.assert_called_with(
                "perplexity_research",
                {"messages": [{"role": "user", "content": "test topic"}]},
            )

    @pytest.mark.asyncio
    async def test_perplexity_reason(self, provider):
        """Test perplexity reasoning method."""
        with (
            patch.object(provider, "_ensure_initialized"),
            patch.object(
                provider.mcp_wrapper, "call_tool", return_value={"result": "reasoning"}
            ) as mock_call,
        ):
            result = await provider.perplexity_reason("test reasoning")

            assert result == {"result": "reasoning"}
            mock_call.assert_called_with(
                "perplexity_reason",
                {"messages": [{"role": "user", "content": "test reasoning"}]},
            )

    def test_get_capabilities(self, provider):
        """Test getting provider capabilities."""
        capabilities = provider.get_capabilities()

        assert "content_types" in capabilities
        assert "news" in capabilities["content_types"]
        assert "current_events" in capabilities["content_types"]
        assert capabilities["features"]["llm_processing"] is True
        assert capabilities["features"]["source_attribution"] is True
        assert capabilities["features"]["reasoning"] is True

    def test_estimate_cost(self, provider):
        """Test cost estimation."""
        basic_query = SearchQuery(query="test", advanced=False)
        advanced_query = SearchQuery(query="test", advanced=True)

        basic_cost = provider.estimate_cost(basic_query)
        advanced_cost = provider.estimate_cost(advanced_query)

        assert basic_cost == 0.015
        assert advanced_cost == 0.03

    @pytest.mark.asyncio
    async def test_check_status_success(self, provider):
        """Test successful status check."""
        with (
            patch.object(provider, "_ensure_initialized"),
            patch.object(
                provider.mcp_wrapper,
                "list_tools",
                return_value=[{"name": "perplexity_ask"}],
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
