"""Exa search provider implementation."""

from typing import Any

import httpx

from ..config import get_settings
from ..models.query import SearchQuery
from ..models.results import SearchResponse, SearchResult
from .base import SearchProvider
from .retry_mixin import RetryMixin


class ExaProvider(SearchProvider, RetryMixin):
    """Exa search provider implementation."""

    name = "exa"

    def __init__(self):
        self.api_key = get_settings().providers.exa.api_key
        self.client = httpx.AsyncClient(
            timeout=get_settings().providers.exa.timeout,
            limits=httpx.Limits(max_connections=20),
        )

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search using Exa API."""
        try:

            @self.with_retry
            async def make_request():
                response = await self.client.post(
                    "https://api.exa.ai/search",
                    headers={
                        "Authorization": f"Bearer {self.api_key.get_secret_value()}"
                    },
                    json={
                        "query": query.query,
                        "numResults": min(
                            query.max_results * 2, 20
                        ),  # Request extra for filtering
                        "useAutoprompt": query.advanced,
                    },
                )
                response.raise_for_status()
                return response

            response = await make_request()
            data = response.json()

            results = []
            for item in data.get("results", []):
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("text", "")[:1000],  # Limit snippet length
                        source="exa",
                        score=item.get("score", 0.0),
                        metadata={
                            "published_date": item.get("publishedDate"),
                            "author": item.get("author"),
                        },
                    )
                )

            return SearchResponse(
                results=results[: query.max_results],  # Limit to max_results
                query=query.query,
                total_results=len(results),
                provider="exa",
                timing_ms=response.elapsed.total_seconds() * 1000,
            )

        except Exception as e:
            # Return empty response
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider="exa",
                error=str(e),
            )

    def get_capabilities(self) -> dict[str, Any]:
        """Return Exa capabilities."""
        return {
            "content_types": ["academic", "research", "general", "technical"],
            "features": {
                "semantic_search": True,
                "highlights": True,
                "auto_prompt": True,
            },
            "quality_metrics": {"simple_qa_score": 0.9004},
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Exa costs ~$0.01 per query
        # More for auto-prompting
        return 0.02 if query.advanced else 0.01

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
