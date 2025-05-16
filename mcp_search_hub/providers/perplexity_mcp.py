"""
Perplexity MCP wrapper provider that embeds the official perplexity-mcp server.
"""

import logging
from typing import Any

from ..models.query import SearchQuery
from ..models.results import SearchResult
from .base_mcp import BaseMCPProvider, ServerType

logger = logging.getLogger(__name__)


class PerplexityMCPProvider(BaseMCPProvider):
    """Wrapper for the Perplexity MCP server using unified base class."""

    def __init__(self, api_key: str | None = None):
        super().__init__(
            name="perplexity",
            api_key=api_key,
            env_var_name="PERPLEXITY_API_KEY",
            server_type=ServerType.NODE_JS,
            args=["perplexity-mcp"],
            tool_name="perplexity_ask",
            api_timeout=20000,
        )

    def _prepare_search_params(self, query: SearchQuery) -> dict[str, Any]:
        """Prepare parameters for Perplexity search."""
        params = {
            "messages": [
                {
                    "role": "user",
                    "content": query.query,
                }
            ]
        }

        # Add advanced search options if present
        if query.advanced:
            # Perplexity supports additional search modes via system message
            if "search_mode" in query.advanced:
                params["messages"].insert(
                    0,
                    {
                        "role": "system",
                        "content": f"Use {query.advanced['search_mode']} search mode",
                    },
                )

            # Add temperature control for more/less creative responses
            if "temperature" in query.advanced:
                params["temperature"] = query.advanced["temperature"]

        return params

    def _process_search_results(
        self, result: Any, query: SearchQuery
    ) -> list[SearchResult]:
        """Process Perplexity search results into standardized format."""
        search_results = []

        try:
            # Handle Perplexity MCP server response format
            if hasattr(result, "content") and result.content:
                if isinstance(result.content, list):
                    for item in result.content:
                        if hasattr(item, "text") and item.text:
                            # Perplexity returns a conversational response
                            # We need to extract relevant information
                            text_content = item.text

                            # Perplexity often includes citations as [1], [2], etc.
                            # Try to parse these
                            import re

                            citation_pattern = r"\[(\d+)\]\s*([^\[]+?)(?=\[|\Z)"
                            citations = re.findall(citation_pattern, text_content)

                            if citations:
                                # Create separate results for each citation
                                for citation_num, citation_text in citations:
                                    # Try to extract title and URL from the citation
                                    # This is a best-effort approach
                                    lines = citation_text.strip().split("\n")
                                    title = (
                                        lines[0]
                                        if lines
                                        else f"Citation [{citation_num}]"
                                    )
                                    content = (
                                        "\n".join(lines[1:])
                                        if len(lines) > 1
                                        else citation_text
                                    )

                                    search_results.append(
                                        SearchResult(
                                            title=title,
                                            url="",  # Perplexity doesn't always provide URLs
                                            snippet=content[:200] + "..."
                                            if len(content) > 200
                                            else content,
                                            source=self.name,
                                            score=1.0,
                                            raw_content=content,
                                            metadata={
                                                "citation_number": citation_num,
                                                "source": "perplexity",
                                            },
                                        )
                                    )
                            else:
                                # No clear citations, create a single result with the whole response
                                # Split response into paragraphs for better structure
                                paragraphs = text_content.split("\n\n")
                                for i, paragraph in enumerate(
                                    paragraphs[: query.max_results]
                                ):
                                    if paragraph.strip():
                                        title = f"Perplexity Result {i + 1}"
                                        if len(paragraph) > 50:
                                            # Try to extract a title from the first line
                                            first_line = paragraph.split("\n")[0]
                                            if len(first_line) < 100:
                                                title = first_line

                                        search_results.append(
                                            SearchResult(
                                                title=title,
                                                url="",
                                                snippet=paragraph[:200] + "..."
                                                if len(paragraph) > 200
                                                else paragraph,
                                                source=self.name,
                                                score=1.0,
                                                raw_content=paragraph,
                                                metadata={
                                                    "paragraph_index": i,
                                                    "source": "perplexity",
                                                },
                                            )
                                        )
                elif hasattr(result.content, "text"):
                    # Handle single text response
                    text_content = result.content.text

                    # Similar parsing logic as above
                    import re

                    citation_pattern = r"\[(\d+)\]\s*([^\[]+?)(?=\[|\Z)"
                    citations = re.findall(citation_pattern, text_content)

                    if citations:
                        for citation_num, citation_text in citations:
                            lines = citation_text.strip().split("\n")
                            title = lines[0] if lines else f"Citation [{citation_num}]"
                            content = (
                                "\n".join(lines[1:])
                                if len(lines) > 1
                                else citation_text
                            )

                            search_results.append(
                                SearchResult(
                                    title=title,
                                    url="",
                                    snippet=content[:200] + "..."
                                    if len(content) > 200
                                    else content,
                                    source=self.name,
                                    score=1.0,
                                    raw_content=content,
                                    metadata={
                                        "citation_number": citation_num,
                                        "source": "perplexity",
                                    },
                                )
                            )
                    else:
                        paragraphs = text_content.split("\n\n")
                        for i, paragraph in enumerate(paragraphs[: query.max_results]):
                            if paragraph.strip():
                                title = f"Perplexity Result {i + 1}"
                                if len(paragraph) > 50:
                                    first_line = paragraph.split("\n")[0]
                                    if len(first_line) < 100:
                                        title = first_line

                                search_results.append(
                                    SearchResult(
                                        title=title,
                                        url="",
                                        snippet=paragraph[:200] + "..."
                                        if len(paragraph) > 200
                                        else paragraph,
                                        source=self.name,
                                        score=1.0,
                                        raw_content=paragraph,
                                        metadata={
                                            "paragraph_index": i,
                                            "source": "perplexity",
                                        },
                                    )
                                )

        except Exception as e:
            logger.error(f"Error processing Perplexity search results: {str(e)}")

        return search_results

    def get_capabilities(self) -> dict[str, Any]:
        """Return Perplexity provider capabilities."""
        return {
            "name": self.name,
            "supports_raw_content": False,  # Perplexity focuses on synthesized answers
            "supports_advanced_search": True,
            "max_results_per_query": 10,
            "features": [
                "conversational_search",
                "multi_turn_queries",
                "citation_extraction",
                "research_synthesis",
                "real_time_information",
                "reasoning_tasks",
            ],
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of a Perplexity search query."""
        # Perplexity pricing model (approximate)
        base_cost = 0.03  # Base cost per search (higher due to LLM processing)

        # Perplexity costs are more about token usage than result count
        # Estimate based on query complexity
        query_length = len(query.query)
        if query_length < 50:
            query_cost = 0.005
        elif query_length < 200:
            query_cost = 0.01
        else:
            query_cost = 0.02

        return base_cost + query_cost
