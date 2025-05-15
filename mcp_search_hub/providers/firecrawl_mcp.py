"""Firecrawl MCP provider implementation.

This provider wraps the official Firecrawl MCP server and exposes its tools
through our Search Hub server.
"""

import os
import subprocess
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import logging

from ..utils.errors import ProviderError
from .base import SearchProvider

logger = logging.getLogger(__name__)


class FirecrawlMCPProvider:
    """Wrapper for the Firecrawl MCP server."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY")
        self.session: Optional[ClientSession] = None
        self.server_params = StdioServerParameters(
            command=["npx", "firecrawl-mcp"],
            args=[],
            env={"FIRECRAWL_API_KEY": self.api_key, **os.environ},
        )

    async def initialize(self):
        """Initialize the connection to Firecrawl MCP server."""
        try:
            # Check if the Firecrawl MCP server is installed
            result = subprocess.run(
                ["npx", "firecrawl-mcp", "--version"], capture_output=True, text=True
            )
            if result.returncode != 0:
                # Install it if not present
                logger.info("Installing Firecrawl MCP server...")
                install_result = subprocess.run(
                    ["npm", "install", "-g", "firecrawl-mcp"],
                    capture_output=True,
                    text=True,
                )
                if install_result.returncode != 0:
                    raise ProviderError(
                        f"Failed to install Firecrawl MCP server: {install_result.stderr}"
                    )
                logger.info("Firecrawl MCP server installed successfully")

            # Connect to the server
            read_stream, write_stream = await stdio_client(self.server_params)
            self.session = await ClientSession(read_stream, write_stream).__aenter__()
            logger.info("Connected to Firecrawl MCP server")

            # Verify server is ready
            server_info = await self.session.get_server_info()
            logger.info(f"Firecrawl MCP server info: {server_info}")

        except Exception as e:
            logger.error(f"Failed to initialize Firecrawl MCP provider: {e}")
            raise ProviderError(f"Failed to initialize Firecrawl MCP provider: {e}")

    async def close(self):
        """Close the connection to Firecrawl MCP server."""
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the Firecrawl MCP server."""
        if not self.session:
            await self.initialize()

        try:
            result = await self.session.call_tool(tool_name, arguments=arguments)
            return result
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise ProviderError(f"Failed to call Firecrawl tool {tool_name}: {e}")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the Firecrawl MCP server."""
        if not self.session:
            await self.initialize()

        try:
            tools = await self.session.list_tools()
            return [tool.model_dump() for tool in tools]
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            raise ProviderError(f"Failed to list Firecrawl tools: {e}")


class FirecrawlProvider(SearchProvider):
    """Search provider that uses the Firecrawl MCP server for web scraping."""

    def __init__(self, **config):
        super().__init__(**config)
        self.mcp_client = FirecrawlMCPProvider(api_key=self.api_key)
        self._initialized = False

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "web_search": False,  # Firecrawl is primarily for scraping
            "structured_data": True,
            "markdown_support": True,
            "screenshot_support": True,
            "javascript_rendering": True,
            "api_limits": {"rate_limit": 100, "max_results": 50},
        }

    async def _ensure_initialized(self):
        """Ensure the MCP client is initialized."""
        if not self._initialized:
            await self.mcp_client.initialize()
            self._initialized = True

    async def search(
        self, query: str, max_results: int = 10, **options
    ) -> List[Dict[str, Any]]:
        """
        Firecrawl doesn't provide traditional search, but can crawl from a URL.
        This method is here for interface compatibility.
        """
        # If query is a URL, we can scrape it
        if query.startswith(("http://", "https://")):
            return await self.scrape_url(query, **options)
        else:
            # For non-URL queries, return empty results
            return []

    async def scrape_url(self, url: str, **options) -> List[Dict[str, Any]]:
        """Scrape a URL using Firecrawl."""
        await self._ensure_initialized()

        try:
            # Call the firecrawl_scrape tool
            result = await self.mcp_client.call_tool(
                "firecrawl_scrape", {"url": url, **options}
            )

            # Convert result to our standard format
            if isinstance(result, dict):
                return [
                    {
                        "title": result.get("title", url),
                        "url": url,
                        "content": result.get("markdown", result.get("content", "")),
                        "metadata": result,
                    }
                ]
            return []

        except Exception as e:
            logger.error(f"Error scraping URL {url}: {e}")
            return []

    async def firecrawl_map(self, url: str, **options) -> Dict[str, Any]:
        """Discover URLs from a starting point."""
        await self._ensure_initialized()
        return await self.mcp_client.call_tool("firecrawl_map", {"url": url, **options})

    async def firecrawl_crawl(self, url: str, **options) -> Dict[str, Any]:
        """Start an asynchronous crawl of multiple pages."""
        await self._ensure_initialized()
        return await self.mcp_client.call_tool(
            "firecrawl_crawl", {"url": url, **options}
        )

    async def firecrawl_check_crawl_status(self, id: str) -> Dict[str, Any]:
        """Check the status of a crawl job."""
        await self._ensure_initialized()
        return await self.mcp_client.call_tool(
            "firecrawl_check_crawl_status", {"id": id}
        )

    async def firecrawl_search(self, query: str, **options) -> Dict[str, Any]:
        """Search and retrieve content from web pages."""
        await self._ensure_initialized()
        return await self.mcp_client.call_tool(
            "firecrawl_search", {"query": query, **options}
        )

    async def firecrawl_extract(self, urls: List[str], **options) -> Dict[str, Any]:
        """Extract structured information from web pages."""
        await self._ensure_initialized()
        return await self.mcp_client.call_tool(
            "firecrawl_extract", {"urls": urls, **options}
        )

    async def firecrawl_deep_research(self, query: str, **options) -> Dict[str, Any]:
        """Conduct deep research on a query."""
        await self._ensure_initialized()
        return await self.mcp_client.call_tool(
            "firecrawl_deep_research", {"query": query, **options}
        )

    async def firecrawl_generate_llmstxt(self, url: str, **options) -> Dict[str, Any]:
        """Generate standardized LLMs.txt file for a URL."""
        await self._ensure_initialized()
        return await self.mcp_client.call_tool(
            "firecrawl_generate_llmstxt", {"url": url, **options}
        )

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available Firecrawl tools."""
        await self._ensure_initialized()
        return await self.mcp_client.list_tools()

    async def close(self):
        """Close the MCP client connection."""
        await self.mcp_client.close()
        self._initialized = False
