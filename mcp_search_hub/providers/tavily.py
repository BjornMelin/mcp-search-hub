"""Tavily search provider implementation."""

import httpx
from typing import Dict, Any
from .base import SearchProvider
from ..models.query import SearchQuery
from ..models.results import SearchResult, SearchResponse
from ..config import get_settings


class TavilyProvider(SearchProvider):
    """Tavily search provider implementation."""

    name = "tavily"

    def __init__(self):
        self.api_key = get_settings().providers.tavily.api_key
        self.client = httpx.AsyncClient(
            timeout=get_settings().providers.tavily.timeout,
            limits=httpx.Limits(max_connections=20),
        )

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search using Tavily API."""
        try:
            search_depth = "advanced" if query.advanced else "basic"

            response = await self.client.post(
                "https://api.tavily.com/search",
                headers={"Content-Type": "application/json"},
                json={
                    "api_key": self.api_key.get_secret_value(),
                    "query": query.query,
                    "search_depth": search_depth,
                    "max_results": query.max_results,
                    "include_raw_content": False,
                    "include_images": False,
                    "topic": "general",
                },
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("results", []):
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        source="tavily",
                        score=item.get("score", 0.0),
                        metadata={
                            "domain": item.get("domain", ""),
                            "published_date": item.get("published_date"),
                        },
                    )
                )

            return SearchResponse(
                results=results,
                query=query.query,
                total_results=len(results),
                provider="tavily",
                timing_ms=0,  # Tavily doesn't provide timing info
            )

        except Exception as e:
            # Return empty response
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider="tavily",
                error=str(e),
            )

    def get_capabilities(self) -> Dict[str, Any]:
        """Return Tavily capabilities."""
        return {
            "content_types": ["general", "technical", "news"],
            "features": {"rag_optimized": True, "content_extraction": True},
            "quality_metrics": {"simple_qa_score": 0.73},
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Tavily costs ~$0.01 per basic search
        # ~$0.02 per advanced search
        return 0.02 if query.advanced else 0.01

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
