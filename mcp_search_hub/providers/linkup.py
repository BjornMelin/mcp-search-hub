"""Linkup search provider implementation."""

from typing import Any

import httpx

from ..config import get_settings
from ..models.query import SearchQuery
from ..models.results import SearchResponse, SearchResult
from .base import SearchProvider
from .retry_mixin import RetryMixin


class LinkupProvider(SearchProvider, RetryMixin):
    """Linkup search provider implementation."""

    name = "linkup"

    def __init__(self):
        self.api_key = get_settings().providers.linkup.api_key
        self.client = httpx.AsyncClient(
            timeout=get_settings().providers.linkup.timeout,
            limits=httpx.Limits(max_connections=20),
        )

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search using Linkup API."""
        depth = "deep" if query.advanced else "standard"

        try:
            # If raw_content is requested, use different output type
            output_type = "detailed" if query.raw_content else "searchResults"

            # Use retry decorator for the API call
            @self.with_retry
            async def make_request():
                response = await self.client.post(
                    "https://api.linkup.ai/search",
                    headers={
                        "Authorization": f"Bearer {self.api_key.get_secret_value()}"
                    },
                    json={
                        "query": query.query,
                        "depth": depth,
                        "output_type": output_type,
                    },
                )
                response.raise_for_status()
                return response

            response = await make_request()
            data = response.json()

            results = []
            for item in data.get("results", []):
                # When raw_content is requested, fetch content or use content field
                raw_content = None
                if query.raw_content:
                    # If 'content' is directly available in the response, use it
                    if "content" in item:
                        raw_content = item["content"]
                    # Otherwise fetch from URL if needed
                    elif query.raw_content and self._should_fetch_content(
                        item.get("url", "")
                    ):
                        raw_content = await self._fetch_content(item.get("url", ""))

                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("snippet", ""),
                        source="linkup",
                        score=item.get("score", 0.0),
                        raw_content=raw_content,
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
                provider="linkup",
                timing_ms=response.elapsed.total_seconds() * 1000,
            )

        except Exception as e:
            # Return empty response
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider="linkup",
                error=str(e),
            )

    def get_capabilities(self) -> dict[str, Any]:
        """Return Linkup capabilities."""
        return {
            "content_types": ["factual", "business", "news", "linkedin"],
            "features": {"deep_search": True, "real_time": True},
            "quality_metrics": {"simple_qa_score": 0.91},
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Standard search cost: ~$0.005 per query
        # Deep search cost: ~$0.05 per query
        return 0.05 if query.advanced else 0.005

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    def _should_fetch_content(self, url: str) -> bool:
        """Determine if content should be fetched for this URL."""
        # Don't fetch content from certain domains or file types
        excluded_domains = ["youtube.com", "vimeo.com", "twitter.com", "facebook.com"]
        excluded_extensions = [
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
        ]

        for domain in excluded_domains:
            if domain in url:
                return False

        return all(not url.endswith(ext) for ext in excluded_extensions)

    async def _fetch_content(self, url: str) -> str:
        """Fetch content from a URL."""
        try:
            # Use Firecrawl scrape API to get content if API key is available
            firecrawl_api_key = get_settings().providers.firecrawl.api_key
            if firecrawl_api_key:

                @self.with_retry
                async def fetch_with_firecrawl():
                    response = await self.client.post(
                        "https://api.firecrawl.dev/scrape",
                        headers={
                            "Authorization": f"Bearer {firecrawl_api_key.get_secret_value()}"
                        },
                        json={
                            "url": url,
                            "formats": ["markdown"],
                            "onlyMainContent": True,
                        },
                        timeout=10.0,
                    )
                    response.raise_for_status()
                    return response

                try:
                    response = await fetch_with_firecrawl()
                    data = response.json()
                    return data.get("markdown", "")
                except Exception:
                    pass  # Fall through to direct fetch

            # Fallback to direct HTTP request if Firecrawl is unavailable
            @self.with_retry
            async def fetch_direct():
                response = await self.client.get(
                    url, timeout=5.0, follow_redirects=True
                )
                response.raise_for_status()
                return response

            response = await fetch_direct()
            if response.is_success:
                content_type = response.headers.get("content-type", "")
                if "text/html" in content_type:
                    # Simple HTML extraction (very basic)
                    text = response.text
                    # Remove script and style elements
                    for tag in ["script", "style"]:
                        start_tag = f"<{tag}"
                        end_tag = f"</{tag}>"
                        while start_tag in text.lower():
                            start_pos = text.lower().find(start_tag)
                            end_pos = text.lower().find(end_tag, start_pos)
                            if end_pos > start_pos:
                                text = text[:start_pos] + text[end_pos + len(end_tag) :]
                            else:
                                break

                    # Very simple HTML to text conversion
                    text = text.replace("<br>", "\n").replace("<br />", "\n")
                    return text[:10000]  # Limit size
                return "Content available but not extractable (non-HTML content)"
            return "Content fetch failed"
        except Exception as e:
            return f"Error fetching content: {str(e)}"
