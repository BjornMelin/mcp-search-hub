"""
Exa MCP wrapper provider that embeds the official exa-mcp-server.
"""

import logging
from typing import Any

from ..models.query import SearchQuery
from ..models.results import SearchResult
from .base_mcp import BaseMCPProvider, ServerType

logger = logging.getLogger(__name__)


class ExaMCPProvider(BaseMCPProvider):
    """Wrapper for the Exa MCP server using unified base class."""

    def __init__(self, api_key: str | None = None):
        super().__init__(
            name="exa",
            api_key=api_key,
            env_var_name="EXA_API_KEY",
            server_type=ServerType.NODE_JS,
            args=["exa-mcp-server"],
            tool_name="web_search_exa",
            api_timeout=15000,
        )

    def _prepare_search_params(self, query: SearchQuery) -> dict[str, Any]:
        """Prepare parameters for Exa search."""
        params = {
            "query": query.query,
            "numResults": query.max_results,
        }

        # Add advanced search options if present
        if query.advanced:
            if "contents" in query.advanced:
                params["contents"] = query.advanced["contents"]
            if "startPublishedDate" in query.advanced:
                params["startPublishedDate"] = query.advanced["startPublishedDate"]
            if "highlights" in query.advanced:
                params["highlights"] = query.advanced["highlights"]

        return params

    def _process_search_results(
        self, result: Any, query: SearchQuery
    ) -> list[SearchResult]:
        """Process Exa search results into standardized format."""
        search_results = []

        try:
            # Handle Exa MCP server response format
            if (
                hasattr(result, "content")
                and result.content
                and isinstance(result.content, list)
            ):
                for item in result.content:
                    if hasattr(item, "text") and item.text:
                        # Parse the text content for search results
                        text_data = item.text

                        # Exa returns a formatted string or JSON, parse accordingly
                        if isinstance(text_data, str) and "results:" in text_data:
                            # Parse formatted string response
                            lines = text_data.split("\n")
                            current_result = {}

                            for line in lines:
                                stripped_line = line.strip()
                                if stripped_line.startswith("Title:"):
                                    if current_result:
                                        search_results.append(
                                            SearchResult(
                                                title=current_result.get("title", ""),
                                                url=current_result.get("url", ""),
                                                snippet=current_result.get(
                                                    "excerpt", ""
                                                ),
                                                source=self.name,
                                                score=float(
                                                    current_result.get(
                                                        "metadata", {}
                                                    ).get("score", 1.0)
                                                )
                                                if current_result.get(
                                                    "metadata", {}
                                                ).get("score")
                                                else 1.0,
                                                raw_content=current_result.get(
                                                    "content"
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
                                    current_result["url"] = stripped_line[4:].strip()
                                elif stripped_line.startswith("Excerpt:"):
                                    current_result["excerpt"] = stripped_line[
                                        8:
                                    ].strip()
                                    current_result["content"] = stripped_line[
                                        8:
                                    ].strip()
                                elif stripped_line.startswith("Published Date:"):
                                    current_result.setdefault("metadata", {})[
                                        "publishedDate"
                                    ] = stripped_line[14:].strip()
                                elif stripped_line.startswith("Author:"):
                                    current_result.setdefault("metadata", {})[
                                        "author"
                                    ] = stripped_line[7:].strip()
                                elif stripped_line.startswith("Score:"):
                                    current_result.setdefault("metadata", {})[
                                        "score"
                                    ] = stripped_line[6:].strip()

                            # Add the last result
                            if current_result:
                                search_results.append(
                                    SearchResult(
                                        title=current_result.get("title", ""),
                                        url=current_result.get("url", ""),
                                        snippet=current_result.get("excerpt", ""),
                                        source=self.name,
                                        score=float(
                                            current_result.get("metadata", {}).get(
                                                "score", 1.0
                                            )
                                        )
                                        if current_result.get("metadata", {}).get(
                                            "score"
                                        )
                                        else 1.0,
                                        raw_content=current_result.get("content"),
                                        metadata=current_result.get("metadata", {}),
                                    )
                                )

                        elif isinstance(text_data, dict) and "results" in text_data:
                            # Parse JSON response format
                            for result_item in text_data["results"]:
                                search_results.append(
                                    SearchResult(
                                        title=result_item.get("title", ""),
                                        url=result_item.get("url", ""),
                                        snippet=result_item.get(
                                            "excerpt", result_item.get("text", "")
                                        ),
                                        source=self.name,
                                        score=float(result_item.get("score", 1.0))
                                        if result_item.get("score")
                                        else 1.0,
                                        raw_content=result_item.get(
                                            "text", result_item.get("excerpt", "")
                                        ),
                                        metadata={
                                            "publishedDate": result_item.get(
                                                "publishedDate"
                                            ),
                                            "author": result_item.get("author"),
                                            "score": result_item.get("score"),
                                        },
                                    )
                                )

        except Exception as e:
            logger.error(f"Error processing Exa search results: {str(e)}")

        return search_results

    def get_capabilities(self) -> dict[str, Any]:
        """Return Exa provider capabilities."""
        return {
            "name": self.name,
            "supports_raw_content": True,
            "supports_advanced_search": True,
            "max_results_per_query": 10,
            "features": [
                "search_filters",
                "date_range_filtering",
                "content_extraction",
                "semantic_search",
                "highlights",
                "research_paper_search",
                "company_research",
                "competitor_finder",
                "linkedin_search",
                "wikipedia_search",
                "github_search",
            ],
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of an Exa search query."""
        # Exa pricing model (approximate)
        base_cost = 0.015  # Base cost per search

        # Additional cost for more results
        results_cost = query.max_results * 0.0005

        # Additional cost for advanced features
        if query.advanced:
            results_cost *= 1.2

        return base_cost + results_cost
