"""
Linkup MCP wrapper provider that embeds the official python-mcp-server.
"""

import asyncio
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import logging

from ..utils.errors import ProviderError
from ..models.query import SearchQuery
from ..models.results import SearchResult, SearchResponse
from ..models.base import HealthStatus
from .base import SearchProvider

logger = logging.getLogger(__name__)


class LinkupMCPProvider:
    """Wrapper for the Linkup Python MCP server using MCP Python SDK."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Linkup MCP provider with configuration."""
        self.api_key = api_key or os.getenv("LINKUP_API_KEY")
        if not self.api_key:
            raise ValueError("Linkup API key is required")

        self.session: Optional[ClientSession] = None
        
        # Since Linkup is already a Python MCP server, we'll run it directly with Python
        self.server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_search_linkup"],
            env={"LINKUP_API_KEY": self.api_key, **os.environ},
        )

    async def _check_installation(self) -> bool:
        """Check if Linkup MCP server is installed."""
        try:
            # Check if the package is installed
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", "mcp-search-linkup"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    async def _install_server(self):
        """Install the Linkup MCP server."""
        logger.info("Installing Linkup MCP server...")
        try:
            install_result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "mcp-search-linkup"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if install_result.returncode != 0:
                raise ProviderError(
                    f"Failed to install Linkup MCP server: {install_result.stderr}"
                )
            logger.info("Linkup MCP server installed successfully")
        except subprocess.TimeoutExpired:
            raise ProviderError("Installation timed out after 60 seconds")
        except Exception as e:
            raise ProviderError(f"Failed to install Linkup MCP server: {e}")

    async def initialize(self):
        """Initialize the connection to Linkup MCP server."""
        try:
            # Check if the Linkup MCP server is installed
            if not await self._check_installation():
                await self._install_server()

            # Connect to the server
            read_stream, write_stream = await stdio_client(self.server_params)
            self.session = await ClientSession(read_stream, write_stream).__aenter__()
            logger.info("Connected to Linkup MCP server")

            # Verify server is ready
            server_info = await self.session.get_server_info()
            logger.info(f"Linkup MCP server info: {server_info}")

        except Exception as e:
            logger.error(f"Failed to initialize Linkup MCP provider: {e}")
            raise ProviderError(f"Failed to initialize Linkup MCP provider: {e}")

    async def close(self):
        """Close the connection to Linkup MCP server."""
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the Linkup MCP server."""
        if not self.session:
            await self.initialize()

        try:
            result = await self.session.call_tool(tool_name, arguments=arguments)
            return result
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise ProviderError(f"Failed to call Linkup tool {tool_name}: {e}")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the Linkup MCP server."""
        if not self.session:
            await self.initialize()

        try:
            tools = await self.session.list_tools()
            return [tool.model_dump() for tool in tools]
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            raise ProviderError(f"Failed to list Linkup tools: {e}")


class LinkupProvider(SearchProvider):
    """Search provider that uses the Linkup MCP server for real-time web search."""

    name = "linkup"

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the Linkup search provider."""
        super().__init__()
        config = config or {}
        self.api_key = config.get("linkup_api_key", os.getenv("LINKUP_API_KEY"))
        self.mcp_wrapper = LinkupMCPProvider(api_key=self.api_key)
        self._initialized = False

    async def _ensure_initialized(self):
        """Ensure the MCP client is initialized."""
        if not self._initialized:
            await self.mcp_wrapper.initialize()
            self._initialized = True

    async def search(self, query: SearchQuery) -> SearchResponse:
        """
        Execute a search using the search-web tool.

        This method provides real-time search functionality through the Linkup MCP server.
        """
        await self._ensure_initialized()

        try:
            # Use search-web tool for search functionality
            result = await self.mcp_wrapper.call_tool(
                "search-web",
                {
                    "query": query.query,
                    "depth": "deep" if query.advanced else "standard",
                },
            )

            # Parse the result and format it as search results
            results = []
            
            # The result is typically a list containing a TextContent object
            if isinstance(result, list) and len(result) > 0:
                text_content = result[0]
                if hasattr(text_content, 'text'):
                    # Parse the text content which contains search results
                    search_data = eval(text_content.text) if text_content.text.startswith('[') else text_content.text
                    
                    if isinstance(search_data, list):
                        for idx, item in enumerate(search_data[:query.max_results]):
                            if isinstance(item, dict):
                                search_result = SearchResult(
                                    title=item.get("title", ""),
                                    url=item.get("url", ""),
                                    snippet=item.get("content", item.get("snippet", "")),
                                    source="linkup",
                                    score=1.0 - (idx * 0.1),  # Decreasing score by position
                                    raw_content=item.get("content", "") if query.raw_content else None,
                                    metadata={
                                        "name": item.get("name", ""),
                                        "type": item.get("type", ""),
                                    },
                                )
                                results.append(search_result)
                    else:
                        # If not a list, create a single result from the text
                        search_result = SearchResult(
                            title=f"Linkup Search: {query.query[:50]}...",
                            url="https://linkup.so",
                            snippet=str(search_data)[:200] + "..." if len(str(search_data)) > 200 else str(search_data),
                            source="linkup",
                            score=1.0,
                            raw_content=str(search_data) if query.raw_content else None,
                            metadata={},
                        )
                        results.append(search_result)

            return SearchResponse(
                results=results[:query.max_results],
                query=query.query,
                total_results=len(results),
                provider="linkup",
                timing_ms=0,  # MCP doesn't provide timing info
            )

        except Exception as e:
            logger.error(f"Linkup search error: {e}")
            # Return error response
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider="linkup",
                error=str(e),
            )

    def get_capabilities(self) -> Dict[str, Any]:
        """Return Linkup capabilities."""
        return {
            "content_types": ["news", "current_events", "general", "premium_content"],
            "features": {
                "real_time": True,
                "premium_sources": True,
                "deep_search": True,
            },
            "quality_metrics": {"real_time_score": 0.95},
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Linkup costs approximately $0.005 per search according to their docs
        return 0.01 if query.advanced else 0.005

    async def check_status(self) -> Tuple[HealthStatus, str]:
        """Check the status of the Linkup provider."""
        try:
            await self._ensure_initialized()
            # Try to list tools to verify connection
            tools = await self.mcp_wrapper.list_tools()
            if tools:
                return HealthStatus.OK, "Linkup provider is operational"
            else:
                return HealthStatus.FAILED, "No tools available from Linkup MCP server"
        except Exception as e:
            logger.error(f"Linkup health check failed: {e}")
            return HealthStatus.FAILED, f"Health check failed: {str(e)}"

    async def cleanup(self):
        """Clean up resources."""
        await self.mcp_wrapper.close()
        self._initialized = False

    async def __aenter__(self):
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()