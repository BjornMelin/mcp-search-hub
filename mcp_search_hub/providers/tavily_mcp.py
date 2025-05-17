"""
Tavily MCP wrapper provider that embeds the official tavily-mcp server.
"""

import logging
from typing import Any

from ..models.query import SearchQuery
from ..models.results import SearchResult
from .base_mcp import BaseMCPProvider, ServerType

logger = logging.getLogger(__name__)


class TavilyMCPProvider(BaseMCPProvider):
    """Wrapper for the Tavily MCP server using unified base class."""

    def __init__(self, api_key: str | None = None):
        super().__init__(
            name="tavily",
            api_key=api_key,
            env_var_name="TAVILY_API_KEY",
            server_type=ServerType.NODE_JS,
            args=["tavily-mcp@0.2.0"],
            tool_name="tavily_search",
            api_timeout=10000,
        )

    def _prepare_search_params(self, query: SearchQuery) -> dict[str, Any]:
        """Prepare parameters for Tavily search."""
        params = {
            "query": query.query,
            "max_results": query.max_results,
            "search_depth": "basic",  # Default search depth
            "include_raw_content": query.raw_content,
        }

        # Add advanced search options if present
        if query.advanced:
            # Tavily supports advanced search depth
            if "search_depth" in query.advanced:
                params["search_depth"] = query.advanced["search_depth"]
            elif query.advanced.get("deep_search", False):
                params["search_depth"] = "advanced"

            # Domain filtering
            if "include_domains" in query.advanced:
                params["include_domains"] = query.advanced["include_domains"]
            if "exclude_domains" in query.advanced:
                params["exclude_domains"] = query.advanced["exclude_domains"]

            # Time range filtering
            if "time_range" in query.advanced:
                params["time_range"] = query.advanced["time_range"]

            # Topic filtering
            if "topic" in query.advanced:
                params["topic"] = query.advanced["topic"]

        return params

    def _process_search_results(
        self, result: Any, query: SearchQuery
    ) -> list[SearchResult]:
        """Process Tavily search results into standardized format."""
        search_results = []

        try:
            # Handle Tavily MCP server response format
            if (
                hasattr(result, "content")
                and result.content
                and isinstance(result.content, list)
            ):
                for item in result.content:
                    if hasattr(item, "text") and item.text:
                        # Parse the text content for search results
                        text_data = item.text

                        # Tavily returns JSON-structured results
                        if isinstance(text_data, dict) and "results" in text_data:
                            for result_item in text_data["results"]:
                                # Extract content based on raw_content request
                                content = ""
                                if query.raw_content and "raw_content" in result_item:
                                    content = result_item["raw_content"]
                                else:
                                    content = result_item.get(
                                        "content", result_item.get("snippet", "")
                                    )

                                search_results.append(
                                    SearchResult(
                                        title=result_item.get("title", ""),
                                        url=result_item.get("url", ""),
                                        snippet=result_item.get("snippet", ""),
                                        source=self.name,
                                        score=float(
                                            result_item.get("relevance_score", 1.0)
                                        )
                                        if result_item.get("relevance_score")
                                        else 1.0,
                                        raw_content=content,
                                        metadata={
                                            "domain": result_item.get("domain"),
                                            "published_date": result_item.get(
                                                "published_date"
                                            ),
                                            "relevance_score": result_item.get(
                                                "relevance_score"
                                            ),
                                            "content_type": result_item.get(
                                                "content_type"
                                            ),
                                        },
                                    )
                                )
                        elif isinstance(text_data, str):
                            # Try parsing as formatted text response
                            import json

                            try:
                                # Tavily might return JSON string
                                json_data = json.loads(text_data)
                                if (
                                    isinstance(json_data, dict)
                                    and "results" in json_data
                                ):
                                    for result_item in json_data["results"]:
                                        content = ""
                                        if (
                                            query.raw_content
                                            and "raw_content" in result_item
                                        ):
                                            content = result_item["raw_content"]
                                        else:
                                            content = result_item.get(
                                                "content",
                                                result_item.get("snippet", ""),
                                            )

                                        search_results.append(
                                            SearchResult(
                                                title=result_item.get("title", ""),
                                                url=result_item.get("url", ""),
                                                snippet=result_item.get("snippet", ""),
                                                source=self.name,
                                                score=float(
                                                    result_item.get(
                                                        "relevance_score", 1.0
                                                    )
                                                )
                                                if result_item.get("relevance_score")
                                                else 1.0,
                                                raw_content=content,
                                                metadata={
                                                    "domain": result_item.get("domain"),
                                                    "published_date": result_item.get(
                                                        "published_date"
                                                    ),
                                                    "relevance_score": result_item.get(
                                                        "relevance_score"
                                                    ),
                                                    "content_type": result_item.get(
                                                        "content_type"
                                                    ),
                                                },
                                            )
                                        )
                            except json.JSONDecodeError:
                                # Fall back to text parsing
                                lines = text_data.split("\n")
                                current_result = {}

                                for line in lines:
                                    stripped_line = line.strip()
                                    if stripped_line.startswith("Title:"):
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
                                                        ).get("relevance_score", 1.0)
                                                    )
                                                    if current_result.get(
                                                        "metadata", {}
                                                    ).get("relevance_score")
                                                    else 1.0,
                                                    raw_content=current_result.get(
                                                        "content", ""
                                                    ),
                                                    metadata=current_result.get(
                                                        "metadata", {}
                                                    ),
                                                )
                                            )
                                        current_result = {
                                            "title": stripped_line[6:].strip()
                                        }
                                    elif stripped_line.startswith("URL:"):
                                        current_result["url"] = stripped_line[
                                            4:
                                        ].strip()
                                    elif stripped_line.startswith("Content:"):
                                        current_result["content"] = stripped_line[
                                            8:
                                        ].strip()
                                    elif stripped_line.startswith("Snippet:"):
                                        current_result["snippet"] = stripped_line[
                                            8:
                                        ].strip()
                                    elif stripped_line.startswith("Domain:"):
                                        current_result.setdefault("metadata", {})[
                                            "domain"
                                        ] = stripped_line[7:].strip()
                                    elif stripped_line.startswith("Date:"):
                                        current_result.setdefault("metadata", {})[
                                            "published_date"
                                        ] = stripped_line[5:].strip()
                                    elif stripped_line.startswith("Score:"):
                                        current_result.setdefault("metadata", {})[
                                            "relevance_score"
                                        ] = stripped_line[6:].strip()

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
                                                    "relevance_score", 1.0
                                                )
                                            )
                                            if current_result.get("metadata", {}).get(
                                                "relevance_score"
                                            )
                                            else 1.0,
                                            raw_content=current_result.get(
                                                "content", ""
                                            ),
                                            metadata=current_result.get("metadata", {}),
                                        )
                                    )

        except Exception as e:
            logger.error(f"Error processing Tavily search results: {str(e)}")

        return search_results

    def get_capabilities(self) -> dict[str, Any]:
        """Return Tavily provider capabilities."""
        return {
            "name": self.name,
            "supports_raw_content": True,
            "supports_advanced_search": True,
            "max_results_per_query": 20,
            "features": [
                "basic_search",
                "advanced_search",
                "domain_filtering",
                "time_range_filtering",
                "topic_categorization",
                "content_extraction",
                "news_search",
                "relevance_scoring",
            ],
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of a Tavily search query."""
        # Tavily pricing model (approximate)
        base_cost = 0.005  # Base cost per search

        # Additional cost for advanced search
        search_cost = base_cost
        if query.advanced and query.advanced.get("search_depth") == "advanced":
            search_cost = 0.015

        # Additional cost for more results
        results_cost = query.max_results * 0.0002

        # Additional cost for raw content
        if query.raw_content:
            results_cost *= 1.5

        return search_cost + results_cost
