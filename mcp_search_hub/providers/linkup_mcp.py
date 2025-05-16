"""
Linkup MCP wrapper provider that embeds the official python-mcp-server.
"""

import asyncio
import logging
from typing import Any

from ..models.query import SearchQuery
from ..models.results import SearchResponse, SearchResult
from ..utils.errors import ProviderError
from .base_mcp import BaseMCPProvider, ServerType
from .retry_mixin import RetryMixin

logger = logging.getLogger(__name__)


class LinkupMCPProvider(BaseMCPProvider, RetryMixin):
    """Wrapper for the Linkup Python MCP server using unified base class."""

    def __init__(self, api_key: str | None = None):
        super().__init__(
            name="linkup",
            api_key=api_key,
            env_var_name="LINKUP_API_KEY",
            server_type=ServerType.PYTHON,
            args=["-m", "mcp_search_linkup"],
            tool_name="linkup_search_web",
            api_timeout=10000,
        )

    def _prepare_search_params(self, query: SearchQuery) -> dict[str, Any]:
        """Prepare parameters for Linkup search."""
        params = {
            "query": query.query,
            "depth": "standard",  # Default depth
        }

        # Linkup supports deep search for more comprehensive results
        if query.advanced:
            if "depth" in query.advanced:
                params["depth"] = query.advanced["depth"]
            elif query.advanced.get("deep_search", False):
                params["depth"] = "deep"

        return params

    def _process_search_results(
        self, result: Any, query: SearchQuery
    ) -> list[SearchResult]:
        """Process Linkup search results into standardized format."""
        search_results = []

        try:
            # Handle direct dictionary response (for testing)
            if isinstance(result, dict) and "results" in result:
                for result_item in result["results"]:
                    search_results.append(
                        SearchResult(
                            title=result_item.get("title", ""),
                            url=result_item.get("url", ""),
                            snippet=result_item.get("snippet", ""),
                            source=self.name,
                            score=float(result_item.get("score", 1.0)),
                            raw_content=result_item.get("content", ""),
                            metadata=result_item.get("metadata", {}),
                        )
                    )
                return search_results

            # Handle Linkup MCP server response format
            if hasattr(result, "content") and result.content:
                if isinstance(result.content, list):
                    for item in result.content:
                        if hasattr(item, "text") and item.text:
                            # Parse the text content for search results
                            text_data = item.text

                            # Linkup returns JSON-like structure in text
                            if isinstance(text_data, dict):
                                if "results" in text_data:
                                    for result_item in text_data["results"]:
                                        search_results.append(
                                            SearchResult(
                                                title=result_item.get("title", ""),
                                                url=result_item.get("url", ""),
                                                snippet=result_item.get(
                                                    "snippet",
                                                    result_item.get("description", ""),
                                                ),
                                                source=self.name,
                                                score=float(
                                                    result_item.get("score", 1.0)
                                                ),
                                                raw_content=result_item.get(
                                                    "content",
                                                    result_item.get("description", ""),
                                                ),
                                                metadata={
                                                    "source": result_item.get("source"),
                                                    "published_date": result_item.get(
                                                        "published_date"
                                                    ),
                                                    "relevance_score": result_item.get(
                                                        "score"
                                                    ),
                                                },
                                            )
                                        )
                            elif isinstance(text_data, str):
                                # Try parsing as formatted text (similar to Exa)
                                lines = text_data.split("\n")
                                current_result = {}

                                for line in lines:
                                    line = line.strip()
                                    if line.startswith("Title:"):
                                        if current_result:
                                            search_results.append(
                                                SearchResult(
                                                    title=current_result.get(
                                                        "title", ""
                                                    ),
                                                    url=current_result.get("url", ""),
                                                    snippet=current_result.get(
                                                        "snippet", ""
                                                    ),
                                                    source=self.name,
                                                    score=float(
                                                        current_result.get(
                                                            "metadata", {}
                                                        ).get("score", 1.0)
                                                    ),
                                                    raw_content=current_result.get(
                                                        "content", ""
                                                    ),
                                                    metadata=current_result.get(
                                                        "metadata", {}
                                                    ),
                                                )
                                            )
                                        current_result = {"title": line[6:].strip()}
                                    elif line.startswith("URL:"):
                                        current_result["url"] = line[4:].strip()
                                    elif line.startswith("Content:") or line.startswith(
                                        "Description:"
                                    ):
                                        current_result["content"] = line[8:].strip()
                                    elif line.startswith("Snippet:"):
                                        current_result["snippet"] = line[8:].strip()
                                    elif line.startswith("Source:"):
                                        current_result.setdefault("metadata", {})[
                                            "source"
                                        ] = line[7:].strip()
                                    elif line.startswith("Date:"):
                                        current_result.setdefault("metadata", {})[
                                            "published_date"
                                        ] = line[5:].strip()

                                # Add the last result
                                if current_result:
                                    search_results.append(
                                        SearchResult(
                                            title=current_result.get("title", ""),
                                            url=current_result.get("url", ""),
                                            snippet=current_result.get("snippet", ""),
                                            source=self.name,
                                            score=float(
                                                current_result.get("metadata", {}).get(
                                                    "score", 1.0
                                                )
                                            ),
                                            raw_content=current_result.get(
                                                "content", ""
                                            ),
                                            metadata=current_result.get("metadata", {}),
                                        )
                                    )

        except Exception as e:
            logger.error(f"Error processing Linkup search results: {str(e)}")

        return search_results

    def get_capabilities(self) -> dict[str, Any]:
        """Return Linkup provider capabilities."""
        return {
            "name": self.name,
            "supports_raw_content": True,
            "supports_advanced_search": True,
            "max_results_per_query": 10,
            "features": [
                "real_time_search",
                "news_aggregation",
                "content_summarization",
                "deep_search_mode",
                "premium_content_access",
                "academic_sources",
            ],
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of a Linkup search query."""
        # Linkup pricing model (approximate)
        base_cost = 0.01  # Base cost per search

        # Additional cost for deep search
        depth_multiplier = 1.0
        if query.advanced and query.advanced.get("depth") == "deep":
            depth_multiplier = 2.0

        # Additional cost for more results
        results_cost = query.max_results * 0.0005

        return (base_cost + results_cost) * depth_multiplier

    async def search(self, query: SearchQuery) -> SearchResponse:
        """
        Execute a search query using the Linkup MCP server with retry logic.

        This overrides the base search method to add exponential backoff retry.

        Args:
            query: The search query to execute

        Returns:
            SearchResponse: The search results
        """
        # Use retry decorator from RetryMixin
        return await self.with_retry(super().search)(query)

    async def _check_installation(self) -> bool:
        """
        Check if the Linkup MCP server is installed.
        For Python packages, we check differently than Node.js packages.
        """
        try:
            import subprocess
            import sys

            # Check if the package is installed
            cmd = [sys.executable, "-c", "import mcp_search_linkup; print('ok')"]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.INSTALLATION_CHECK_TIMEOUT
                )
                return process.returncode == 0 and b"ok" in stdout
            except TimeoutError:
                logger.warning(f"Installation check for {self.name} timed out")
                if process.returncode is None:
                    process.kill()
                return False

        except Exception as e:
            logger.info(f"{self.name} MCP server not found: {str(e)}")
            return False

    async def _install_server(self) -> None:
        """Install the Linkup Python MCP server if not already installed."""
        logger.info(f"Installing {self.name} MCP server...")

        import subprocess
        import sys

        # Install the package
        cmd = [sys.executable, "-m", "pip", "install", "mcp-search-linkup"]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown installation error"
            raise ProviderError(
                f"Failed to install {self.name} MCP server: {error_msg}"
            )

        logger.info(f"Successfully installed {self.name} MCP server")
