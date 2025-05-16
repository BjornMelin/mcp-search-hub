"""Firecrawl MCP provider implementation.

This provider wraps the official Firecrawl MCP server and exposes its tools
through our Search Hub server.
"""

import logging
from typing import Any

from ..models.query import SearchQuery
from ..models.results import SearchResult
from .base_mcp import BaseMCPProvider, ServerType

logger = logging.getLogger(__name__)


class FirecrawlMCPProvider(BaseMCPProvider):
    """Wrapper for the Firecrawl MCP server."""

    def __init__(self, api_key: str | None = None):
        super().__init__(
            name="firecrawl",
            api_key=api_key,
            env_var_name="FIRECRAWL_API_KEY",
            server_type=ServerType.NODE_JS,
            args=["firecrawl-mcp"],
            tool_name="firecrawl_search",
            api_timeout=30000,
        )

    def _prepare_search_params(self, query: SearchQuery) -> dict[str, Any]:
        """Prepare parameters for Firecrawl search."""
        params = {
            "query": query.query,
            "max_results": query.max_results,
            "include_raw_content": query.raw_content,
        }

        # Add advanced search options if present
        if query.advanced:
            params["search_params"] = {
                "includes": query.advanced.get("includes", []),
                "excludes": query.advanced.get("excludes", []),
            }

        return params

    def _process_search_results(
        self, result: Any, query: SearchQuery
    ) -> list[SearchResult]:
        """Process Firecrawl search results into standardized format."""
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

            # Handle Firecrawl MCP server response format
            if hasattr(result, "content") and result.content:
                if isinstance(result.content, list):
                    for item in result.content:
                        if hasattr(item, "text") and item.text:
                            # Parse the text content for search results
                            results_data = item.text
                            if (
                                isinstance(results_data, dict)
                                and "results" in results_data
                            ):
                                for result_item in results_data["results"]:
                                    content = result_item.get("markdown", "")

                                    # If raw content is requested but markdown is not available,
                                    # use raw HTML
                                    if (
                                        query.raw_content
                                        and not content
                                        and "rawHtml" in result_item
                                    ):
                                        content = result_item["rawHtml"]

                                    search_results.append(
                                        SearchResult(
                                            title=result_item.get("title", ""),
                                            url=result_item.get("url", ""),
                                            snippet=result_item.get("excerpt", ""),
                                            source=self.name,
                                            score=float(result_item.get("score", 1.0)),
                                            raw_content=content,
                                            metadata=result_item.get("metadata", {}),
                                        )
                                    )
                elif hasattr(result.content, "text"):
                    # Handle single text response
                    text_data = result.content.text
                    if isinstance(text_data, dict) and "results" in text_data:
                        for result_item in text_data["results"]:
                            content = result_item.get("markdown", "")

                            # If raw content is requested but markdown is not available,
                            # use raw HTML
                            if (
                                query.raw_content
                                and not content
                                and "rawHtml" in result_item
                            ):
                                content = result_item["rawHtml"]

                            search_results.append(
                                SearchResult(
                                    title=result_item.get("title", ""),
                                    url=result_item.get("url", ""),
                                    snippet=result_item.get("excerpt", ""),
                                    source=self.name,
                                    score=float(result_item.get("score", 1.0)),
                                    raw_content=content,
                                    metadata=result_item.get("metadata", {}),
                                )
                            )
        except Exception as e:
            logger.error(f"Error processing Firecrawl search results: {str(e)}")

        return search_results

    def get_capabilities(self) -> dict[str, Any]:
        """Return Firecrawl provider capabilities."""
        return {
            "name": self.name,
            "supports_raw_content": True,
            "supports_advanced_search": True,
            "max_results_per_query": 10,
            "features": [
                "web_scraping",
                "markdown_extraction",
                "html_parsing",
                "sitemap_crawling",
                "deep_research",
            ],
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of a Firecrawl search query."""
        # Firecrawl pricing model (approximate)
        base_cost = 0.02  # Base cost per search

        # Additional cost for more results
        results_cost = query.max_results * 0.001

        # Additional cost for raw content
        if query.raw_content:
            results_cost *= 1.5

        return base_cost + results_cost
