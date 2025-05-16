"""
Test suite for Perplexity MCP provider integration.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.models.results import SearchResponse
from mcp_search_hub.providers.perplexity_mcp import PerplexityMCPProvider
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
            await provider._cleanup()

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
        with patch(
            "mcp_search_hub.providers.base_mcp.asyncio.create_subprocess_exec"
        ) as mock_create_subprocess:
            # Mock process with successful return code and output
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"ok", b""))
            mock_create_subprocess.return_value = mock_process

            result = await provider._check_installation()
            assert result is True
            mock_create_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_installation_failure(self, provider):
        """Test failed installation check."""
        with patch(
            "mcp_search_hub.providers.base_mcp.asyncio.create_subprocess_exec"
        ) as mock_create_subprocess:
            # Mock process with failed return code
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(return_value=(b"", b"not found"))
            mock_create_subprocess.return_value = mock_process

            result = await provider._check_installation()
            assert result is False

    @pytest.mark.asyncio
    async def test_install_server_success(self, provider):
        """Test successful server installation."""
        with patch(
            "mcp_search_hub.providers.base_mcp.asyncio.create_subprocess_exec"
        ) as mock_create_subprocess:
            # Mock process with successful return code
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"success", b""))
            mock_create_subprocess.return_value = mock_process

            await provider._install_server()
            mock_create_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_install_server_failure(self, provider):
        """Test failed server installation."""
        with patch(
            "mcp_search_hub.providers.base_mcp.asyncio.create_subprocess_exec"
        ) as mock_create_subprocess:
            # Mock process with failed return code
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(
                return_value=(b"", b"Installation failed")
            )
            mock_create_subprocess.return_value = mock_process

            with pytest.raises(ProviderError):
                await provider._install_server()

    @pytest.mark.asyncio
    async def test_initialize_success(self, provider):
        """Test successful initialization."""
        with patch.object(provider, "_check_installation", return_value=True):
            with patch("mcp_search_hub.providers.base_mcp.stdio_client") as mock_stdio:
                # Mock the stdio streams and session
                mock_read_stream = MagicMock()
                mock_write_stream = MagicMock()

                async def mock_stdio_client(*args, **kwargs):
                    return (mock_read_stream, mock_write_stream)

                mock_stdio.side_effect = mock_stdio_client

                mock_session = AsyncMock()
                # Mock tools
                mock_tool = MagicMock()
                mock_tool.name = "perplexity_ask"
                mock_session.list_tools = AsyncMock(return_value=[mock_tool])

                with patch(
                    "mcp_search_hub.providers.base_mcp.ClientSession"
                ) as mock_client_session:
                    mock_client_session.return_value = mock_session
                    mock_client_session.return_value.__aenter__ = AsyncMock(
                        return_value=mock_session
                    )

                    await provider.initialize()
                    assert provider.session == mock_session

    @pytest.mark.asyncio
    async def test_initialize_with_installation(self, provider):
        """Test initialization with installation needed."""
        # First time check_installation returns False (not installed)
        # Second time returns True (after installation)
        check_installation_mock = AsyncMock(side_effect=[False, True])

        with patch.object(
            provider, "_check_installation", side_effect=check_installation_mock
        ):
            with patch.object(provider, "_install_server") as mock_install:
                with patch(
                    "mcp_search_hub.providers.base_mcp.stdio_client"
                ) as mock_stdio:
                    # Mock the stdio streams and session
                    mock_read_stream = MagicMock()
                    mock_write_stream = MagicMock()

                    async def mock_stdio_client(*args, **kwargs):
                        return (mock_read_stream, mock_write_stream)

                    mock_stdio.side_effect = mock_stdio_client

                    mock_session = AsyncMock()
                    # Mock tools
                    mock_tool = MagicMock()
                    mock_tool.name = "perplexity_ask"
                    mock_session.list_tools = AsyncMock(return_value=[mock_tool])

                    with patch(
                        "mcp_search_hub.providers.base_mcp.ClientSession"
                    ) as mock_client_session:
                        mock_client_session.return_value = mock_session
                        mock_client_session.return_value.__aenter__ = AsyncMock(
                            return_value=mock_session
                        )

                        await provider.initialize()
                        mock_install.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_success(self, provider):
        """Test successful tool calling."""
        provider.session = AsyncMock()

        # Mock the content structure
        mock_content = MagicMock()
        mock_content.text = "Success result"
        mock_tool_result = MagicMock()
        mock_tool_result.content = [mock_content]
        provider.session.call_tool.return_value = mock_tool_result

        query = SearchQuery(query="test query", max_results=10)
        result = await provider.search(query)
        assert isinstance(result, SearchResponse)
        assert result.query == "test query"
        assert result.provider == "perplexity"

    @pytest.mark.asyncio
    async def test_search_error(self, provider):
        """Test tool calling error."""
        provider.session = AsyncMock()
        provider.session.call_tool.side_effect = Exception("Tool error")

        query = SearchQuery(query="test query", max_results=10)
        result = await provider.search(query)
        # In BaseMCPProvider, search doesn't raise but returns SearchResponse with error
        assert isinstance(result, SearchResponse)
        assert result.error is not None
        assert "Tool error" in result.error

    @pytest.mark.asyncio
    async def test_list_tools_success(self, provider):
        """Test successful tools listing."""
        provider.session = AsyncMock()
        mock_tool = MagicMock()
        mock_tool.name = "perplexity_ask"
        provider.session.list_tools.return_value = [mock_tool]

        status, message = await provider.check_status()
        assert status.value == "ok"
        assert "is operational" in message

    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test closing connection."""
        mock_session = MagicMock()
        provider.session = mock_session

        await provider._cleanup()
        assert provider.session is None
