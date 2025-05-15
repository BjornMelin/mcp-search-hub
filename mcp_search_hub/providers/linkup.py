"""Linkup search provider implementation."""

import httpx
from typing import Dict, Any, List, Optional
from .base import SearchProvider
from ..models.query import SearchQuery
from ..models.results import SearchResult, SearchResponse
from ..config import get_settings


class LinkupProvider(SearchProvider):
    """Linkup search provider implementation."""
    
    name = "linkup"
    
    def __init__(self):
        self.api_key = get_settings().providers.linkup.api_key
        self.client = httpx.AsyncClient(
            timeout=get_settings().providers.linkup.timeout,
            limits=httpx.Limits(max_connections=20)
        )
    
    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search using Linkup API."""
        depth = "deep" if query.advanced else "standard"
        
        try:
            response = await self.client.post(
                "https://api.linkup.ai/search",
                headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
                json={
                    "query": query.query,
                    "depth": depth,
                    "output_type": "searchResults"
                }
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("results", []):
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("snippet", ""),
                        source="linkup",
                        score=item.get("score", 0.0),
                        metadata={
                            "domain": item.get("domain", ""),
                            "published_date": item.get("published_date")
                        }
                    )
                )
            
            return SearchResponse(
                results=results,
                query=query.query,
                total_results=len(results),
                provider="linkup",
                timing_ms=response.elapsed.total_seconds() * 1000
            )
            
        except Exception as e:
            # Return empty response
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider="linkup",
                error=str(e)
            )
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Return Linkup capabilities."""
        return {
            "content_types": ["factual", "business", "news", "linkedin"],
            "features": {
                "deep_search": True,
                "real_time": True
            },
            "quality_metrics": {
                "simple_qa_score": 0.91
            }
        }
    
    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Standard search cost: ~$0.005 per query
        # Deep search cost: ~$0.05 per query
        return 0.05 if query.advanced else 0.005
        
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()