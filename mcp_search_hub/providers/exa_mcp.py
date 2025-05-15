"""
Exa MCP wrapper provider that embeds the official exa-mcp-server.
"""

import os
import subprocess
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


class ExaMCPProvider:
    """Wrapper for the Exa MCP server using MCP Python SDK."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Exa MCP provider with configuration."""
        self.api_key = api_key or os.getenv("EXA_API_KEY")
        if not self.api_key:
            raise ValueError("Exa API key is required")

        self.session: Optional[ClientSession] = None
        self.server_params = StdioServerParameters(
            command="npx",
            args=["@modelcontextprotocol/server-exa"],
            env={"EXA_API_KEY": self.api_key, **os.environ},
        )

    async def initialize(self):
        """Initialize the connection to Exa MCP server."""
        try:
            # Check if the Exa MCP server is installed
            result = subprocess.run(
                ["npx", "@modelcontextprotocol/server-exa", "--version"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                # Install it if not present
                logger.info("Installing Exa MCP server...")
                install_result = subprocess.run(
                    ["npm", "install", "-g", "@modelcontextprotocol/server-exa"],
                    capture_output=True,
                    text=True,
                )
                if install_result.returncode != 0:
                    raise ProviderError(
                        f"Failed to install Exa MCP server: {install_result.stderr}"
                    )
                logger.info("Exa MCP server installed successfully")

            # Connect to the server
            read_stream, write_stream = await stdio_client(self.server_params)
            self.session = await ClientSession(read_stream, write_stream).__aenter__()
            logger.info("Connected to Exa MCP server")

            # Verify server is ready
            server_info = await self.session.get_server_info()
            logger.info(f"Exa MCP server info: {server_info}")

        except Exception as e:
            logger.error(f"Failed to initialize Exa MCP provider: {e}")
            raise ProviderError(f"Failed to initialize Exa MCP provider: {e}")

    async def close(self):
        """Close the connection to Exa MCP server."""
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the Exa MCP server."""
        if not self.session:
            await self.initialize()

        try:
            result = await self.session.call_tool(tool_name, arguments=arguments)
            return result
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise ProviderError(f"Failed to call Exa tool {tool_name}: {e}")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the Exa MCP server."""
        if not self.session:
            await self.initialize()

        try:
            tools = await self.session.list_tools()
            return [tool.model_dump() for tool in tools]
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            raise ProviderError(f"Failed to list Exa tools: {e}")


class ExaProvider(SearchProvider):
    """Search provider that uses the Exa MCP server for advanced search capabilities."""

    name = "exa"

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Exa search provider."""
        super().__init__()
        self.api_key = config.get("exa_api_key", "")
        self.mcp_wrapper = ExaMCPProvider(api_key=self.api_key)
        self._initialized = False

    async def _ensure_initialized(self):
        """Ensure the MCP client is initialized."""
        if not self._initialized:
            await self.mcp_wrapper.initialize()
            self._initialized = True

    async def search(self, query: SearchQuery) -> SearchResponse:
        """
        Execute a search using the web_search_exa tool.

        This method provides basic search functionality through the Exa MCP server.
        """
        await self._ensure_initialized()

        try:
            # Use web_search_exa for general search functionality
            result = await self.mcp_wrapper.call_tool(
                "web_search_exa", {"query": query.query, "limit": query.max_results}
            )

            # Parse the result and format it as search results
            results = []
            if isinstance(result, dict) and "results" in result:
                raw_results = result["results"]
                if isinstance(raw_results, list):
                    for item in raw_results[: query.max_results]:
                        search_result = SearchResult(
                            title=item.get("title", ""),
                            url=item.get("url", ""),
                            snippet=item.get("snippet", ""),
                            content=item.get("text", "") if query.raw_content else "",
                            source="exa",
                            score=item.get("score", 0.0),
                            metadata={
                                "published_date": item.get("publishedDate", ""),
                                "author": item.get("author", ""),
                            },
                        )
                        results.append(search_result)

            return SearchResponse(
                results=results,
                query=query.query,
                total_results=len(results),
                provider="exa",
                timing_ms=0,  # MCP doesn't provide timing info
            )

        except Exception as e:
            logger.error(f"Exa search error: {e}")
            # Return error response
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider="exa",
                error=str(e),
            )

    async def research_papers(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Search for research papers using Exa."""
        await self._ensure_initialized()
        return await self.mcp_wrapper.call_tool(
            "research_paper_search", {"query": query, **kwargs}
        )

    async def company_research(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Research companies using Exa."""
        await self._ensure_initialized()
        return await self.mcp_wrapper.call_tool(
            "company_research", {"query": query, **kwargs}
        )

    async def competitor_finder(self, company: str, **kwargs) -> List[Dict[str, Any]]:
        """Find competitors for a company using Exa."""
        await self._ensure_initialized()
        return await self.mcp_wrapper.call_tool(
            "competitor_finder", {"company": company, **kwargs}
        )

    async def linkedin_search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Search LinkedIn using Exa."""
        await self._ensure_initialized()
        return await self.mcp_wrapper.call_tool(
            "linkedin_search", {"query": query, **kwargs}
        )

    async def wikipedia_search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Search Wikipedia using Exa."""
        await self._ensure_initialized()
        return await self.mcp_wrapper.call_tool(
            "wikipedia_search_exa", {"query": query, **kwargs}
        )

    async def github_search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Search GitHub using Exa."""
        await self._ensure_initialized()
        return await self.mcp_wrapper.call_tool(
            "github_search", {"query": query, **kwargs}
        )

    async def crawl(self, url: str, **kwargs) -> Dict[str, Any]:
        """Crawl a URL using Exa."""
        await self._ensure_initialized()
        return await self.mcp_wrapper.call_tool("crawling", {"url": url, **kwargs})

    def get_capabilities(self) -> Dict[str, Any]:
        """Return Exa capabilities."""
        return {
            "content_types": [
                "research_papers",
                "companies",
                "linkedin",
                "wikipedia",
                "github",
                "general",
            ],
            "features": {
                "semantic_search": True,
                "specialized_search": True,
                "real_time": True,
                "crawling": True,
            },
            "quality_metrics": {"semantic_search_score": 0.92},
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Exa costs ~$0.02 per search
        return 0.02

    async def check_status(self) -> Tuple[HealthStatus, str]:
        """Check the status of the Exa provider."""
        try:
            await self._ensure_initialized()
            # Try to list tools to verify connection
            await self.mcp_wrapper.list_tools()
            return HealthStatus.OK, "Exa provider is operational"
        except Exception as e:
            logger.error(f"Exa health check failed: {e}")
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
