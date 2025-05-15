"""
Perplexity MCP wrapper provider that embeds the official perplexity-mcp server.
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


class PerplexityMCPProvider:
    """Wrapper for the Perplexity MCP server using MCP Python SDK."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Perplexity MCP provider with configuration."""
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        if not self.api_key:
            raise ValueError("Perplexity API key is required")

        self.session: Optional[ClientSession] = None
        self.server_params = StdioServerParameters(
            command="npx",
            args=["perplexity-mcp"],
            env={"PERPLEXITY_API_KEY": self.api_key, **os.environ},
        )

    async def _check_installation(self) -> bool:
        """Check if Perplexity MCP server is installed."""
        try:
            result = subprocess.run(
                ["npx", "perplexity-mcp", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    async def _install_server(self):
        """Install the Perplexity MCP server."""
        logger.info("Installing Perplexity MCP server...")
        try:
            install_result = subprocess.run(
                ["npm", "install", "-g", "perplexity-mcp"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if install_result.returncode != 0:
                raise ProviderError(
                    f"Failed to install Perplexity MCP server: {install_result.stderr}"
                )
            logger.info("Perplexity MCP server installed successfully")
        except subprocess.TimeoutExpired:
            raise ProviderError("Installation timed out after 60 seconds")
        except Exception as e:
            raise ProviderError(f"Failed to install Perplexity MCP server: {e}")

    async def initialize(self):
        """Initialize the connection to Perplexity MCP server."""
        try:
            # Check if the Perplexity MCP server is installed
            if not await self._check_installation():
                await self._install_server()

            # Connect to the server
            read_stream, write_stream = await stdio_client(self.server_params)
            self.session = await ClientSession(read_stream, write_stream).__aenter__()
            logger.info("Connected to Perplexity MCP server")

            # Verify server is ready
            server_info = await self.session.get_server_info()
            logger.info(f"Perplexity MCP server info: {server_info}")

        except Exception as e:
            logger.error(f"Failed to initialize Perplexity MCP provider: {e}")
            raise ProviderError(f"Failed to initialize Perplexity MCP provider: {e}")

    async def close(self):
        """Close the connection to Perplexity MCP server."""
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the Perplexity MCP server."""
        if not self.session:
            await self.initialize()

        try:
            result = await self.session.call_tool(tool_name, arguments=arguments)
            return result
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise ProviderError(f"Failed to call Perplexity tool {tool_name}: {e}")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the Perplexity MCP server."""
        if not self.session:
            await self.initialize()

        try:
            tools = await self.session.list_tools()
            return [tool.model_dump() for tool in tools]
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            raise ProviderError(f"Failed to list Perplexity tools: {e}")


class PerplexityProvider(SearchProvider):
    """Search provider that uses the Perplexity MCP server for AI-powered search."""

    name = "perplexity"

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Perplexity search provider."""
        super().__init__()
        self.api_key = config.get("perplexity_api_key", "")
        self.mcp_wrapper = PerplexityMCPProvider(api_key=self.api_key)
        self._initialized = False

    async def _ensure_initialized(self):
        """Ensure the MCP client is initialized."""
        if not self._initialized:
            await self.mcp_wrapper.initialize()
            self._initialized = True

    async def search(self, query: SearchQuery) -> SearchResponse:
        """
        Execute a search using the perplexity_ask tool.

        This method provides basic search functionality through the Perplexity MCP server.
        """
        await self._ensure_initialized()

        try:
            # Use perplexity_ask for general search functionality
            result = await self.mcp_wrapper.call_tool(
                "perplexity_ask",
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a search assistant. Provide web search results only, not summaries or answers. Include source URLs when available.",
                        },
                        {"role": "user", "content": query.query},
                    ]
                },
            )

            # Parse the result and format it as search results
            results = []
            
            # Extract sources from the response if available
            if isinstance(result, dict):
                sources = result.get("sources", [])
                citations = result.get("citations", [])
                content = result.get("content", "")
                
                # Process sources
                for idx, source in enumerate(sources):
                    search_result = SearchResult(
                        title=source.get("title", ""),
                        url=source.get("url", ""),
                        snippet=source.get("snippet", ""),
                        raw_content=content if query.raw_content else None,
                        source="perplexity",
                        score=1.0 - (idx * 0.1),  # Decreasing score by position
                        metadata={
                            "source_id": source.get("id", ""),
                            "domain": source.get("domain", ""),
                            "published_date": source.get("published_date", ""),
                        },
                    )
                    results.append(search_result)
                
                # If no sources but we have content, create a single result
                if not sources and content:
                    search_result = SearchResult(
                        title=f"Perplexity Answer: {query.query[:50]}...",
                        url="https://perplexity.ai",
                        snippet=content[:200] + "..." if len(content) > 200 else content,
                        raw_content=content if query.raw_content else None,
                        source="perplexity",
                        score=1.0,
                        metadata={"citations": citations},
                    )
                    results.append(search_result)

            return SearchResponse(
                results=results[:query.max_results],
                query=query.query,
                total_results=len(results),
                provider="perplexity",
                timing_ms=0,  # MCP doesn't provide timing info
            )

        except Exception as e:
            logger.error(f"Perplexity search error: {e}")
            # Return error response
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider="perplexity",
                error=str(e),
            )

    async def perplexity_research(self, query: str, **kwargs) -> Dict[str, Any]:
        """Perform deep research using Perplexity."""
        await self._ensure_initialized()
        return await self.mcp_wrapper.call_tool(
            "perplexity_research",
            {
                "messages": [
                    {"role": "user", "content": query}
                ],
                **kwargs
            }
        )

    async def perplexity_reason(self, query: str, **kwargs) -> Dict[str, Any]:
        """Perform reasoning tasks using Perplexity."""
        await self._ensure_initialized()
        return await self.mcp_wrapper.call_tool(
            "perplexity_reason",
            {
                "messages": [
                    {"role": "user", "content": query}
                ],
                **kwargs
            }
        )

    def get_capabilities(self) -> Dict[str, Any]:
        """Return Perplexity capabilities."""
        return {
            "content_types": ["news", "current_events", "general", "technical"],
            "features": {
                "llm_processing": True,
                "source_attribution": True,
                "real_time": True,
                "reasoning": True,
                "research": True,
            },
            "quality_metrics": {"simple_qa_score": 0.86},
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Perplexity costs ~$0.015 per query for basic, ~$0.03 for advanced
        return 0.03 if query.advanced else 0.015

    async def check_status(self) -> Tuple[HealthStatus, str]:
        """Check the status of the Perplexity provider."""
        try:
            await self._ensure_initialized()
            # Try to list tools to verify connection
            tools = await self.mcp_wrapper.list_tools()
            if tools:
                return HealthStatus.OK, "Perplexity provider is operational"
            else:
                return HealthStatus.FAILED, "No tools available from Perplexity MCP server"
        except Exception as e:
            logger.error(f"Perplexity health check failed: {e}")
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