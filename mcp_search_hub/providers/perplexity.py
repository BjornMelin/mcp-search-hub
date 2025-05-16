"""Perplexity search provider implementation."""

from typing import Any

import httpx

from ..config import get_settings
from ..models.query import SearchQuery
from ..models.results import SearchResponse, SearchResult
from .base import SearchProvider


class PerplexityProvider(SearchProvider):
    """Perplexity search provider implementation."""

    name = "perplexity"

    def __init__(self):
        self.api_key = get_settings().providers.perplexity.api_key
        self.client = httpx.AsyncClient(
            timeout=get_settings().providers.perplexity.timeout,
            limits=httpx.Limits(max_connections=20),
        )

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search using Perplexity API."""
        try:
            response = await self.client.post(
                "https://api.perplexity.ai/ask",
                headers={
                    "Authorization": f"Bearer {self.api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a search assistant. Provide web search results only, not summaries or answers.",
                        },
                        {"role": "user", "content": query.query},
                    ],
                    "model": "sonar-online",
                    "include_sources": True,
                    "search_focus": "search_focus" if query.advanced else "balanced",
                },
            )
            response.raise_for_status()
            data = response.json()

            results = []

            # Extract sources from response
            sources = data.get("sources", [])
            for source in sources:
                result = SearchResult(
                    title=source.get("title", ""),
                    url=source.get("url", ""),
                    snippet=source.get("snippet", ""),
                    source="perplexity",
                    score=1.0,  # Perplexity doesn't provide scores, use default
                    metadata={
                        "source_id": source.get("id"),
                        "domain": source.get("domain", ""),
                    },
                )
                results.append(result)

            return SearchResponse(
                results=results[: query.max_results],
                query=query.query,
                total_results=len(results),
                provider="perplexity",
                timing_ms=0,  # Perplexity doesn't provide timing info
            )

        except Exception as e:
            # Return empty response
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider="perplexity",
                error=str(e),
            )

    def get_capabilities(self) -> dict[str, Any]:
        """Return Perplexity capabilities."""
        return {
            "content_types": ["news", "current_events", "general", "technical"],
            "features": {
                "llm_processing": True,
                "source_attribution": True,
                "real_time": True,
            },
            "quality_metrics": {"simple_qa_score": 0.86},
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Perplexity costs ~$0.015 per query
        return 0.03 if query.advanced else 0.015

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
