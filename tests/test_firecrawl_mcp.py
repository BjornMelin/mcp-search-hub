"""Tests for Firecrawl MCP provider integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_search_hub.models.base import HealthStatus
from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.providers.firecrawl_mcp import FirecrawlMCPProvider
from mcp_search_hub.utils.errors import ProviderError


@pytest.fixture
def firecrawl_mcp_provider():
    """Create a Firecrawl MCP provider instance."""
    return FirecrawlMCPProvider(api_key="test-api-key")


class TestFirecrawlMCPProvider:
    """Test Firecrawl MCP provider functionality."""

    @pytest.mark.asyncio
    async def test_initialize_success(self, firecrawl_mcp_provider):
        """Test successful initialization."""
        with (
            patch(
                "mcp_search_hub.providers.base_mcp.asyncio.create_subprocess_exec"
            ) as mock_create_subprocess,
            patch(
                "mcp_search_hub.providers.base_mcp.stdio_client", new_callable=AsyncMock
            ) as mock_client,
            patch(
                "mcp_search_hub.providers.base_mcp.ClientSession"
            ) as mock_session_class,
        ):
            # Mock version check success
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_create_subprocess.return_value = mock_process

            # Mock stdio client - async function that returns a tuple
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_client.return_value = (mock_read, mock_write)

            # Mock session
            mock_session = AsyncMock()
            mock_session.get_server_info = AsyncMock(
                return_value={"name": "firecrawl-mcp"}
            )

            # Mock tools
            mock_tool = MagicMock()
            mock_tool.name = "firecrawl_search"
            mock_session.list_tools = AsyncMock(return_value=[mock_tool])
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_class.return_value = mock_session

            await firecrawl_mcp_provider.initialize()

            # Verify initialization
            assert firecrawl_mcp_provider.session is not None
            mock_session.list_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_install_server(self, firecrawl_mcp_provider):
        """Test initialization with server installation."""
        with (
            patch(
                "mcp_search_hub.providers.base_mcp.asyncio.create_subprocess_exec"
            ) as mock_create_subprocess,
            patch(
                "mcp_search_hub.providers.base_mcp.stdio_client", new_callable=AsyncMock
            ) as mock_client,
            patch(
                "mcp_search_hub.providers.base_mcp.ClientSession"
            ) as mock_session_class,
        ):
            # Mock version check failure (server not installed)
            # First subprocess call - version check fails
            mock_process_check = AsyncMock()
            mock_process_check.returncode = 1
            mock_process_check.communicate = AsyncMock(return_value=(b"", b""))

            # Second subprocess call - installation succeeds
            mock_process_install = AsyncMock()
            mock_process_install.returncode = 0
            mock_process_install.communicate = AsyncMock(return_value=(b"", b""))

            # Third subprocess call - version check succeeds
            mock_process_check2 = AsyncMock()
            mock_process_check2.returncode = 0
            mock_process_check2.communicate = AsyncMock(return_value=(b"", b""))

            mock_create_subprocess.side_effect = [
                mock_process_check,  # First check fails
                mock_process_install,  # Install succeeds
                mock_process_check2,  # Second check succeeds
            ]

            # Mock stdio client - async function that returns a tuple
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_client.return_value = (mock_read, mock_write)

            # Mock session
            mock_session = AsyncMock()
            mock_session.get_server_info = AsyncMock(
                return_value={"name": "firecrawl-mcp"}
            )

            # Mock tools for installation test
            mock_tool = MagicMock()
            mock_tool.name = "firecrawl_search"
            mock_session.list_tools = AsyncMock(return_value=[mock_tool])
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_class.return_value = mock_session

            await firecrawl_mcp_provider.initialize()

            # Verify npm install was called
            assert (
                mock_create_subprocess.call_count >= 3
            )  # Version check, install, and version check again

    @pytest.mark.asyncio
    async def test_initialize_failure(self, firecrawl_mcp_provider):
        """Test initialization failure."""
        with patch(
            "mcp_search_hub.providers.base_mcp.asyncio.create_subprocess_exec",
            side_effect=Exception("Connection failed"),
        ):
            with pytest.raises(ProviderError):
                await firecrawl_mcp_provider.initialize()

    @pytest.mark.asyncio
    async def test_search_success(self, firecrawl_mcp_provider):
        """Test successful search."""
        # Mock session
        mock_session = AsyncMock()
        mock_result = {
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com",
                    "snippet": "Test snippet",
                    "score": 0.9,
                }
            ]
        }
        mock_session.call_tool = AsyncMock(return_value=mock_result)
        firecrawl_mcp_provider.session = mock_session

        query = SearchQuery(query="test query", max_results=10)
        response = await firecrawl_mcp_provider.search(query)

        assert len(response.results) > 0
        assert response.provider == "firecrawl"
        mock_session.call_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_not_initialized(self, firecrawl_mcp_provider):
        """Test searching when not initialized."""
        # Mock session to be set after initialization
        mock_session = AsyncMock()
        mock_result = {
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com",
                    "snippet": "Test snippet",
                    "score": 0.9,
                }
            ]
        }
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        async def mock_initialize() -> None:
            firecrawl_mcp_provider.session = mock_session

        with patch.object(
            firecrawl_mcp_provider, "initialize", side_effect=mock_initialize
        ) as mock_init:
            firecrawl_mcp_provider.session = None
            query = SearchQuery(query="test query", max_results=10)
            response = await firecrawl_mcp_provider.search(query)

            mock_init.assert_called_once()
            assert response.provider == "firecrawl"

    @pytest.mark.asyncio
    async def test_search_error(self, firecrawl_mcp_provider):
        """Test search error."""
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(side_effect=Exception("Tool error"))
        firecrawl_mcp_provider.session = mock_session

        query = SearchQuery(query="test query", max_results=10)
        response = await firecrawl_mcp_provider.search(query)

        assert response.error is not None
        assert "Tool error" in response.error

    @pytest.mark.asyncio
    async def test_check_status(self, firecrawl_mcp_provider):
        """Test checking status."""
        # Mock session
        mock_session = AsyncMock()

        # Mock tools
        mock_tool = MagicMock()
        mock_tool.name = "firecrawl_search"
        mock_session.list_tools = AsyncMock(return_value=[mock_tool])

        firecrawl_mcp_provider.session = mock_session

        status, message = await firecrawl_mcp_provider.check_status()

        assert status == HealthStatus.OK
        assert message == "firecrawl MCP server is operational"

    @pytest.mark.asyncio
    async def test_cleanup(self, firecrawl_mcp_provider):
        """Test cleanup functionality."""
        # Mock session
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()
        firecrawl_mcp_provider.session = mock_session

        await firecrawl_mcp_provider._cleanup()

        mock_session.close.assert_called_once()
        assert firecrawl_mcp_provider.session is None
