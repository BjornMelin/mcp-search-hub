"""
Tavily MCP wrapper provider that embeds the official tavily-mcp server.
"""

import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..models.base import HealthStatus
from ..models.query import SearchQuery
from ..models.results import SearchResponse, SearchResult
from ..utils.errors import ProviderError
from .base import SearchProvider

logger = logging.getLogger(__name__)


class TavilyMCPProvider:
    """Wrapper for the Tavily MCP server using MCP Python SDK."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Tavily MCP provider with configuration."""
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            raise ValueError("Tavily API key is required")

        self.session: Optional[ClientSession] = None
        self.server_params = StdioServerParameters(
            command="npx",
            args=["-y", "tavily-mcp@0.2.0"],
            env={"TAVILY_API_KEY": self.api_key, **os.environ},
        )

    async def _check_installation(self) -> bool:
        """Check if the Tavily MCP server is installed."""
        try:
            # Check if the package is installed
            result = subprocess.run(
                ["npx", "-y", "tavily-mcp@0.2.0", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    async def _install_server(self):
        """Install the Tavily MCP server."""
        logger.info("Installing Tavily MCP server...")
        try:
            install_result = subprocess.run(
                ["npm", "install", "-g", "tavily-mcp@0.2.0"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if install_result.returncode != 0:
                raise ProviderError(
                    f"Failed to install Tavily MCP server: {install_result.stderr}"
                )
            logger.info("Tavily MCP server installed successfully")
        except subprocess.TimeoutExpired:
            raise ProviderError("Installation timed out after 60 seconds")
        except Exception as e:
            raise ProviderError(f"Failed to install Tavily MCP server: {e}")

    async def initialize(self):
        """Initialize the connection to Tavily MCP server."""
        try:
            # Check if the Tavily MCP server is installed
            if not await self._check_installation():
                await self._install_server()

            # Connect to the server
            read_stream, write_stream = await stdio_client(self.server_params)
            self.session = await ClientSession(read_stream, write_stream).__aenter__()
            logger.info("Connected to Tavily MCP server")

            # Verify server is ready
            server_info = await self.session.get_server_info()
            logger.info(f"Tavily MCP server info: {server_info}")

        except Exception as e:
            logger.error(f"Failed to initialize Tavily MCP provider: {e}")
            raise ProviderError(f"Failed to initialize Tavily MCP provider: {e}")

    async def close(self):
        """Close the connection to Tavily MCP server."""
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the Tavily MCP server."""
        if not self.session:
            await self.initialize()

        try:
            result = await self.session.call_tool(tool_name, arguments=arguments)
            return result
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise ProviderError(f"Failed to call Tavily tool {tool_name}: {e}")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the Tavily MCP server."""
        if not self.session:
            await self.initialize()

        try:
            tools = await self.session.list_tools()
            return [tool.model_dump() for tool in tools]
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            raise ProviderError(f"Failed to list Tavily tools: {e}")


class TavilyProvider(SearchProvider):
    """Search provider that uses the Tavily MCP server for search and content extraction."""

    name = "tavily"

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the Tavily search provider."""
        super().__init__()
        config = config or {}
        self.api_key = config.get("tavily_api_key", os.getenv("TAVILY_API_KEY"))
        self.mcp_wrapper = TavilyMCPProvider(api_key=self.api_key)
        self._initialized = False

    async def _ensure_initialized(self):
        """Ensure the MCP client is initialized."""
        if not self._initialized:
            await self.mcp_wrapper.initialize()
            self._initialized = True

    async def search(self, query: SearchQuery) -> SearchResponse:
        """
        Execute a search using the tavily-search tool.

        This method provides search functionality through the Tavily MCP server.
        """
        await self._ensure_initialized()

        try:
            # Use tavily-search for search functionality
            search_depth = "advanced" if query.advanced else "basic"

            result = await self.mcp_wrapper.call_tool(
                "tavily-search",
                {
                    "query": query.query,
                    "options": {
                        "searchDepth": search_depth,
                        "maxResults": query.max_results,
                        "includeRawContent": query.raw_content,
                        "includeImages": False,
                    },
                },
            )

            # Parse the result and format it as search results
            results = []

            # Process the results based on the MCP response format
            if isinstance(result, dict) and "content" in result:
                content_items = result.get("content", [])
                for item in content_items:
                    if item.get("type") == "text" and item.get("text"):
                        # Parse the text content
                        try:
                            import json

                            search_data = json.loads(item.get("text"))

                            if "results" in search_data:
                                for idx, result_item in enumerate(
                                    search_data["results"][: query.max_results]
                                ):
                                    search_result = SearchResult(
                                        title=result_item.get("title", ""),
                                        url=result_item.get("url", ""),
                                        snippet=result_item.get("content", ""),
                                        source="tavily",
                                        score=1.0
                                        - (idx * 0.05),  # Decreasing score by position
                                        raw_content=result_item.get("raw_content", "")
                                        if query.raw_content
                                        else None,
                                        metadata={
                                            "domain": result_item.get("domain", ""),
                                            "published_date": result_item.get(
                                                "published_date", ""
                                            ),
                                        },
                                    )
                                    results.append(search_result)
                        except (json.JSONDecodeError, ValueError):
                            # If we can't parse JSON, use the raw text as a single result
                            search_result = SearchResult(
                                title=f"Tavily Search: {query.query[:50]}...",
                                url="https://tavily.com",
                                snippet=item.get("text", "")[:200] + "..."
                                if len(item.get("text", "")) > 200
                                else item.get("text", ""),
                                source="tavily",
                                score=1.0,
                                raw_content=item.get("text", "")
                                if query.raw_content
                                else None,
                                metadata={},
                            )
                            results.append(search_result)

            return SearchResponse(
                results=results[: query.max_results],
                query=query.query,
                total_results=len(results),
                provider="tavily",
                timing_ms=0,  # MCP doesn't provide timing info
            )

        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            # Return error response
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider="tavily",
                error=str(e),
            )

    async def extract_content(self, url: str, **kwargs) -> Dict[str, Any]:
        """
        Extract content from a URL using the tavily-extract tool.

        Args:
            url: The URL to extract content from
            **kwargs: Additional options for extraction
        """
        await self._ensure_initialized()

        options = {"extractDepth": "advanced", **kwargs}
        result = await self.mcp_wrapper.call_tool(
            "tavily-extract",
            {"urls": [url] if isinstance(url, str) else url, "options": options},
        )
        return result

    def get_capabilities(self) -> Dict[str, Any]:
        """Return Tavily capabilities."""
        return {
            "content_types": ["general", "technical", "news", "academic"],
            "features": {
                "rag_optimized": True,
                "content_extraction": True,
                "advanced_search": True,
            },
            "quality_metrics": {
                "rag_score": 0.88,
                "extraction_quality": 0.92,
            },
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Tavily costs ~$0.01 per basic search
        # ~$0.02 per advanced search
        return 0.02 if query.advanced else 0.01

    async def check_status(self) -> Tuple[HealthStatus, str]:
        """Check the status of the Tavily provider."""
        try:
            await self._ensure_initialized()
            # Try to list tools to verify connection
            tools = await self.mcp_wrapper.list_tools()
            if tools:
                return HealthStatus.OK, "Tavily provider is operational"
            else:
                return (
                    HealthStatus.DEGRADED,
                    "No tools available from Tavily MCP server",
                )
        except Exception as e:
            logger.error(f"Tavily health check failed: {e}")
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
