"""Firecrawl search provider implementation."""

import httpx
from typing import Dict, Any, List, Optional
from .base import SearchProvider
from ..models.query import SearchQuery
from ..models.results import SearchResult, SearchResponse
from ..config import get_settings


class FirecrawlProvider(SearchProvider):
    """Firecrawl search provider implementation."""
    
    name = "firecrawl"
    
    def __init__(self):
        self.api_key = get_settings().providers.firecrawl.api_key
        self.client = httpx.AsyncClient(
            timeout=get_settings().providers.firecrawl.timeout,
            limits=httpx.Limits(max_connections=10)
        )
    
    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search using Firecrawl API."""
        try:
            # If query appears to be about content extraction, use scrape endpoint
            if self._is_extraction_query(query.query):
                return await self._handle_extraction_query(query)
            
            # Otherwise use search
            response = await self.client.post(
                "https://api.firecrawl.dev/search",
                headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
                json={
                    "query": query.query,
                    "limit": query.max_results,
                    "scrapeOptions": {
                        "formats": ["markdown"],
                        "onlyMainContent": True
                    } if query.advanced else None
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
                        snippet=item.get("description", ""),
                        source="firecrawl",
                        score=0.5,  # Firecrawl doesn't provide scores, use default
                        metadata={
                            "content": item.get("content", ""),
                            "source_type": "search_result"
                        }
                    )
                )
            
            return SearchResponse(
                results=results,
                query=query.query,
                total_results=len(results),
                provider="firecrawl",
                timing_ms=0  # Firecrawl doesn't provide timing info
            )
            
        except Exception as e:
            # Return empty response
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider="firecrawl",
                error=str(e)
            )
    
    async def _handle_extraction_query(self, query: SearchQuery) -> SearchResponse:
        """Handle a content extraction query."""
        # Extract URL from query if possible
        url = self._extract_url_from_query(query.query)
        
        if not url:
            # If no URL found, try to search for it
            search_response = await self.client.post(
                "https://api.firecrawl.dev/search",
                headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
                json={"query": query.query, "limit": 1}
            )
            search_data = search_response.json()
            if search_data.get("results"):
                url = search_data["results"][0].get("url")
        
        if not url:
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider="firecrawl",
                error="No URL found to extract content from"
            )
        
        # Now scrape the content
        scrape_response = await self.client.post(
            "https://api.firecrawl.dev/scrape",
            headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
            json={
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": True
            }
        )
        scrape_data = scrape_response.json()
        
        # Create a single result with the extracted content
        results = [
            SearchResult(
                title=scrape_data.get("title", url),
                url=url,
                snippet=scrape_data.get("markdown", "")[:500] + "...",
                source="firecrawl",
                score=1.0,
                metadata={
                    "content": scrape_data.get("markdown", ""),
                    "source_type": "extracted_content"
                }
            )
        ]
        
        return SearchResponse(
            results=results,
            query=query.query,
            total_results=len(results),
            provider="firecrawl",
            timing_ms=0
        )
    
    def _is_extraction_query(self, query: str) -> bool:
        """Determine if a query is asking for content extraction."""
        extraction_keywords = [
            "extract", "scrape", "content of", "text from", 
            "get content", "get information from", "website content",
            "page content"
        ]
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in extraction_keywords)
    
    def _extract_url_from_query(self, query: str) -> Optional[str]:
        """Try to extract a URL from the query."""
        # Simple URL extraction
        words = query.split()
        for word in words:
            if word.startswith(("http://", "https://")):
                return word
            if word.startswith("www.") and "." in word[4:]:
                return "https://" + word
        return None
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Return Firecrawl capabilities."""
        return {
            "content_types": ["web_content", "extraction", "general"],
            "features": {
                "content_extraction": True,
                "scraping": True,
                "deep_research": True
            },
            "quality_metrics": {
                "extraction_quality": 0.95
            }
        }
    
    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Firecrawl costs ~$0.02 per search
        # ~$0.05 per content extraction
        extraction_query = self._is_extraction_query(query.query)
        return 0.05 if extraction_query else 0.02
        
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()