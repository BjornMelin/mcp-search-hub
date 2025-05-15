"""Tests for Exa MCP provider integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_search_hub.providers.exa_mcp import ExaMCPProvider, ExaProvider
from mcp_search_hub.utils.errors import ProviderError
from mcp_search_hub.models.query import SearchQuery


@pytest.fixture
def exa_mcp_provider():
    """Create an Exa MCP provider instance."""
    return ExaMCPProvider(api_key="test-api-key")


@pytest.fixture
def exa_provider():
    """Create an Exa provider instance."""
    return ExaProvider({"exa_api_key": "test-api-key"})


class TestExaMCPProvider:
    """Test Exa MCP provider functionality."""

    @pytest.mark.asyncio
    async def test_initialize_success(self, exa_mcp_provider):
        """Test successful initialization."""
        with (
            patch("subprocess.run") as mock_run,
            patch("mcp_search_hub.providers.exa_mcp.stdio_client", new_callable=AsyncMock) as mock_client,
            patch(
                "mcp_search_hub.providers.exa_mcp.ClientSession"
            ) as mock_session_class,
        ):
            # Mock version check success
            mock_run.return_value = MagicMock(returncode=0)

            # Mock stdio client - async function that returns a tuple
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_client.return_value = (mock_read, mock_write)

            # Mock session
            mock_session = AsyncMock()
            mock_session.get_server_info = AsyncMock(
                return_value={"name": "exa-mcp-server"}
            )
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_class.return_value = mock_session

            await exa_mcp_provider.initialize()

            # Verify initialization
            assert exa_mcp_provider.session is not None
            mock_session.get_server_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_install_server(self, exa_mcp_provider):
        """Test initialization with server installation."""
        with (
            patch("subprocess.run") as mock_run,
            patch("mcp_search_hub.providers.exa_mcp.stdio_client", new_callable=AsyncMock) as mock_client,
            patch(
                "mcp_search_hub.providers.exa_mcp.ClientSession"
            ) as mock_session_class,
        ):
            # Mock version check failure (server not installed)
            mock_run.side_effect = [
                MagicMock(returncode=1),  # Version check fails
                MagicMock(returncode=0),  # Install succeeds
            ]

            # Mock stdio client - async function that returns a tuple
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_client.return_value = (mock_read, mock_write)

            # Mock session
            mock_session = AsyncMock()
            mock_session.get_server_info = AsyncMock(
                return_value={"name": "exa-mcp-server"}
            )
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_class.return_value = mock_session

            await exa_mcp_provider.initialize()

            # Verify npm install was called
            assert mock_run.call_count >= 2  # Version check and install

    @pytest.mark.asyncio
    async def test_initialize_failure(self, exa_mcp_provider):
        """Test initialization failure."""
        with patch("subprocess.run", side_effect=Exception("Connection failed")):
            with pytest.raises(ProviderError):
                await exa_mcp_provider.initialize()

    @pytest.mark.asyncio
    async def test_call_tool_success(self, exa_mcp_provider):
        """Test successful tool invocation."""
        # Mock session
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value={"content": [{"type": "text", "text": "Search results"}]}
        )
        exa_mcp_provider.session = mock_session

        result = await exa_mcp_provider.call_tool("web_search_exa", {"query": "test"})

        assert result == {"content": [{"type": "text", "text": "Search results"}]}
        mock_session.call_tool.assert_called_once_with(
            "web_search_exa", arguments={"query": "test"}
        )

    @pytest.mark.asyncio
    async def test_call_tool_not_initialized(self, exa_mcp_provider):
        """Test calling tool when not initialized."""
        # Mock session to be set after initialization
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value={"result": "test"})
        
        async def mock_initialize():
            exa_mcp_provider.session = mock_session
            
        with patch.object(exa_mcp_provider, "initialize", side_effect=mock_initialize) as mock_init:
            exa_mcp_provider.session = None
            result = await exa_mcp_provider.call_tool("web_search_exa", {"query": "test"})
            
            mock_init.assert_called_once()
            assert result == {"result": "test"}

    @pytest.mark.asyncio
    async def test_call_tool_error(self, exa_mcp_provider):
        """Test tool invocation error."""
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(side_effect=Exception("Tool error"))
        exa_mcp_provider.session = mock_session

        with pytest.raises(ProviderError):
            await exa_mcp_provider.call_tool("web_search_exa", {})

    @pytest.mark.asyncio
    async def test_list_tools(self, exa_mcp_provider):
        """Test listing tools."""
        # Mock session
        mock_session = AsyncMock()
        mock_tool1 = MagicMock()
        mock_tool1.model_dump.return_value = {"name": "tool1"}
        mock_tool2 = MagicMock()
        mock_tool2.model_dump.return_value = {"name": "tool2"}
        mock_session.list_tools = AsyncMock(return_value=[mock_tool1, mock_tool2])
        exa_mcp_provider.session = mock_session

        tools = await exa_mcp_provider.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "tool1"
        assert tools[1]["name"] == "tool2"

    @pytest.mark.asyncio
    async def test_close(self, exa_mcp_provider):
        """Test cleanup functionality."""
        # Mock session
        mock_session = AsyncMock()
        mock_session.__aexit__ = AsyncMock()
        exa_mcp_provider.session = mock_session

        await exa_mcp_provider.close()

        mock_session.__aexit__.assert_called_once_with(None, None, None)
        assert exa_mcp_provider.session is None


class TestExaProvider:
    """Test Exa provider functionality."""

    @pytest.mark.asyncio
    async def test_search_success(self, exa_provider):
        """Test successful search."""
        # Mock MCP wrapper
        mock_wrapper = AsyncMock()
        mock_wrapper.call_tool = AsyncMock(
            return_value={
                "results": [
                    {
                        "title": "Test Result",
                        "url": "https://example.com",
                        "snippet": "Test snippet",
                        "text": "Full content",
                        "score": 0.95,
                    }
                ]
            }
        )
        exa_provider.mcp_wrapper = mock_wrapper
        exa_provider._initialized = True

        query = SearchQuery(query="test query", max_results=10)
        response = await exa_provider.search(query)

        assert len(response.results) == 1
        assert response.results[0].title == "Test Result"
        assert response.results[0].score == 0.95
        assert response.provider == "exa"
        mock_wrapper.call_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_research_papers(self, exa_provider):
        """Test research papers search."""
        mock_wrapper = AsyncMock()
        mock_wrapper.call_tool = AsyncMock(return_value={"papers": []})
        exa_provider.mcp_wrapper = mock_wrapper
        exa_provider._initialized = True

        await exa_provider.research_papers("machine learning")

        mock_wrapper.call_tool.assert_called_once_with(
            "research_paper_search", {"query": "machine learning"}
        )

    @pytest.mark.asyncio
    async def test_company_research(self, exa_provider):
        """Test company research."""
        mock_wrapper = AsyncMock()
        mock_wrapper.call_tool = AsyncMock(return_value={"companies": []})
        exa_provider.mcp_wrapper = mock_wrapper
        exa_provider._initialized = True

        await exa_provider.company_research("tech companies")

        mock_wrapper.call_tool.assert_called_once_with(
            "company_research", {"query": "tech companies"}
        )

    @pytest.mark.asyncio
    async def test_ensure_initialized(self, exa_provider):
        """Test initialization check."""
        mock_wrapper = AsyncMock()
        mock_wrapper.initialize = AsyncMock()
        exa_provider.mcp_wrapper = mock_wrapper
        exa_provider._initialized = False

        await exa_provider._ensure_initialized()

        assert exa_provider._initialized
        mock_wrapper.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup(self, exa_provider):
        """Test provider cleanup."""
        mock_wrapper = AsyncMock()
        mock_wrapper.close = AsyncMock()
        exa_provider.mcp_wrapper = mock_wrapper
        exa_provider._initialized = True

        await exa_provider.cleanup()

        assert not exa_provider._initialized
        mock_wrapper.close.assert_called_once()

    def test_get_capabilities(self, exa_provider):
        """Test getting provider capabilities."""
        capabilities = exa_provider.get_capabilities()

        assert "content_types" in capabilities
        assert "features" in capabilities
        assert "semantic_search" in capabilities["features"]
        assert capabilities["features"]["semantic_search"] is True

    def test_estimate_cost(self, exa_provider):
        """Test cost estimation."""
        cost = exa_provider.estimate_cost("test query")
        assert cost == 0.02
