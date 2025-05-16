"""Firecrawl search provider implementation."""

from typing import Any

import httpx
from pydantic import BaseModel

from ..config import get_settings
from ..models.base import HealthStatus
from ..models.query import SearchQuery
from ..models.results import SearchResponse, SearchResult
from .base import SearchProvider


class MapOptions(BaseModel):
    """Options for URL discovery."""

    ignore_sitemap: bool = False
    include_subdomains: bool = False
    limit: int | None = None
    search: str | None = None
    sitemap_only: bool = False


class CrawlOptions(BaseModel):
    """Options for website crawling."""

    limit: int = 10
    max_depth: int | None = None
    include_paths: list[str] | None = None
    exclude_paths: list[str] | None = None
    allow_external_links: bool = False
    scrape_options: dict[str, Any] | None = None


class ExtractOptions(BaseModel):
    """Options for structured data extraction."""

    prompt: str | None = None
    schema: dict[str, Any] | None = None
    system_prompt: str | None = None
    enable_web_search: bool = False


class DeepResearchOptions(BaseModel):
    """Options for deep research."""

    max_depth: int | None = None
    max_urls: int | None = None
    time_limit: int | None = None


class LLMsTxtOptions(BaseModel):
    """Options for LLMs.txt generation."""

    max_urls: int | None = None
    show_full_text: bool = False


class FirecrawlProvider(SearchProvider):
    """Firecrawl search provider implementation."""

    name = "firecrawl"

    def __init__(self):
        self.api_key = get_settings().providers.firecrawl.api_key
        self.client = httpx.AsyncClient(
            timeout=get_settings().providers.firecrawl.timeout,
            limits=httpx.Limits(max_connections=10),
        )

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search using Firecrawl API."""
        try:
            # If query appears to be about content extraction, use scrape endpoint
            if self._is_extraction_query(query.query):
                return await self._handle_extraction_query(query)

            # Otherwise use search
            search_options = {
                "query": query.query,
                "limit": query.max_results,
            }

            # Always include scrape options if raw_content is requested
            if query.raw_content or query.advanced:
                search_options["scrapeOptions"] = {
                    "formats": (
                        ["markdown", "html"] if query.raw_content else ["markdown"]
                    ),
                    "onlyMainContent": True,
                }

            response = await self.client.post(
                "https://api.firecrawl.dev/v1/search",
                headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
                json=search_options,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("results", []):
                # For Firecrawl, content might be directly available in the result
                raw_content = None
                if query.raw_content:
                    # If we requested raw content and it's available in the response
                    if "content" in item and item["content"]:
                        raw_content = item["content"]
                    elif "html" in item and item["html"]:
                        raw_content = item["html"]
                    elif "markdown" in item and item["markdown"]:
                        raw_content = item["markdown"]

                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("description", ""),
                        source="firecrawl",
                        score=0.5,  # Firecrawl doesn't provide scores, use default
                        raw_content=raw_content,
                        metadata={
                            "content": item.get("content", ""),
                            "source_type": "search_result",
                        },
                    )
                )

            return SearchResponse(
                results=results,
                query=query.query,
                total_results=len(results),
                provider="firecrawl",
                timing_ms=0,  # Firecrawl doesn't provide timing info
            )

        except Exception as e:
            # Return empty response
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider="firecrawl",
                error=str(e),
            )

    async def _handle_extraction_query(self, query: SearchQuery) -> SearchResponse:
        """Handle a content extraction query."""
        # Extract URL from query if possible
        url = self._extract_url_from_query(query.query)

        if not url:
            # If no URL found, try to search for it
            search_response = await self.client.post(
                "https://api.firecrawl.dev/v1/search",
                headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
                json={"query": query.query, "limit": 1},
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
                error="No URL found to extract content from",
            )

        # Now scrape the content
        scrape_response = await self.client.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
        )
        scrape_data = scrape_response.json()

        # Create a single result with the extracted content
        markdown_content = scrape_data.get("markdown", "")
        snippet = (
            markdown_content[:500] + "..."
            if markdown_content
            else "No content extracted"
        )

        # Include raw_content if requested
        raw_content = None
        if query.raw_content:
            if "html" in scrape_data and scrape_data["html"]:
                raw_content = scrape_data["html"]
            elif markdown_content:
                raw_content = markdown_content

        results = [
            SearchResult(
                title=scrape_data.get("title", url),
                url=url,
                snippet=snippet,
                source="firecrawl",
                score=1.0,
                raw_content=raw_content,
                metadata={
                    "content": markdown_content,
                    "source_type": "extracted_content",
                },
            )
        ]

        return SearchResponse(
            results=results,
            query=query.query,
            total_results=len(results),
            provider="firecrawl",
            timing_ms=0,
        )

    async def firecrawl_map(
        self, url: str, options: MapOptions | None = None
    ) -> dict[str, Any]:
        """
        Discover URLs from a starting point.

        Args:
            url: Starting URL for URL discovery
            options: Optional configuration options

        Returns:
            Dictionary containing discovered URLs and metadata
        """
        options = options or MapOptions()

        try:
            map_params = {
                "url": url,
                "ignoreSitemap": options.ignore_sitemap,
                "includeSubdomains": options.include_subdomains,
                "sitemapOnly": options.sitemap_only,
            }

            if options.limit:
                map_params["limit"] = options.limit

            if options.search:
                map_params["search"] = options.search

            response = await self.client.post(
                "https://api.firecrawl.dev/v1/map",
                headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
                json=map_params,
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"error": str(e), "success": False}

    async def firecrawl_crawl(
        self, url: str, options: CrawlOptions | None = None
    ) -> dict[str, Any]:
        """
        Start an asynchronous crawl of multiple pages from a starting URL.

        Args:
            url: Starting URL for the crawl
            options: Optional configuration for the crawl

        Returns:
            Dictionary containing crawl job ID and status
        """
        options = options or CrawlOptions()

        try:
            crawl_params = {
                "url": url,
                "limit": options.limit,
            }

            if options.max_depth is not None:
                crawl_params["maxDepth"] = options.max_depth

            if options.include_paths:
                crawl_params["includePaths"] = options.include_paths

            if options.exclude_paths:
                crawl_params["excludePaths"] = options.exclude_paths

            if options.allow_external_links:
                crawl_params["allowExternalLinks"] = options.allow_external_links

            if options.scrape_options:
                crawl_params["scrapeOptions"] = options.scrape_options

            response = await self.client.post(
                "https://api.firecrawl.dev/v1/crawl",
                headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
                json=crawl_params,
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"error": str(e), "success": False}

    async def firecrawl_check_crawl_status(self, crawl_id: str) -> dict[str, Any]:
        """
        Check the status of a crawl job.

        Args:
            crawl_id: ID of the crawl job to check

        Returns:
            Dictionary containing crawl job status and results if complete
        """
        try:
            response = await self.client.get(
                f"https://api.firecrawl.dev/v1/crawl/{crawl_id}",
                headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"error": str(e), "success": False}

    async def firecrawl_extract(
        self, urls: list[str], options: ExtractOptions | None = None
    ) -> dict[str, Any]:
        """
        Extract structured information from web pages using LLM.

        Args:
            urls: List of URLs to extract information from
            options: Options for extraction

        Returns:
            Dictionary containing extracted structured data
        """
        options = options or ExtractOptions()

        try:
            extract_params = {
                "urls": urls,
            }

            if options.prompt:
                extract_params["prompt"] = options.prompt

            if options.schema:
                extract_params["schema"] = options.schema

            if options.system_prompt:
                extract_params["systemPrompt"] = options.system_prompt

            if options.enable_web_search:
                extract_params["enableWebSearch"] = options.enable_web_search

            response = await self.client.post(
                "https://api.firecrawl.dev/v1/extract",
                headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
                json=extract_params,
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"error": str(e), "success": False}

    async def firecrawl_deep_research(
        self, query: str, options: DeepResearchOptions | None = None
    ) -> dict[str, Any]:
        """
        Conduct deep research on a query using web crawling, search, and AI analysis.

        Args:
            query: The query to research
            options: Configuration options for the research

        Returns:
            Dictionary containing research results
        """
        options = options or DeepResearchOptions()

        try:
            research_params = {
                "query": query,
            }

            if options.max_depth:
                research_params["maxDepth"] = options.max_depth

            if options.max_urls:
                research_params["maxUrls"] = options.max_urls

            if options.time_limit:
                research_params["timeLimit"] = options.time_limit

            response = await self.client.post(
                "https://api.firecrawl.dev/v1/deep-research",
                headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
                json=research_params,
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"error": str(e), "success": False}

    async def firecrawl_generate_llmstxt(
        self, url: str, options: LLMsTxtOptions | None = None
    ) -> dict[str, Any]:
        """
        Generate standardized LLMs.txt file for a given URL, which provides
        context about how LLMs should interact with the website.

        Args:
            url: The URL to generate LLMs.txt from
            options: Configuration options

        Returns:
            Dictionary containing the generated LLMs.txt content
        """
        options = options or LLMsTxtOptions()

        try:
            llmstxt_params = {
                "url": url,
            }

            if options.max_urls:
                llmstxt_params["maxUrls"] = options.max_urls

            if options.show_full_text:
                llmstxt_params["showFullText"] = options.show_full_text

            response = await self.client.post(
                "https://api.firecrawl.dev/v1/generate-llmstxt",
                headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
                json=llmstxt_params,
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"error": str(e), "success": False}

    def _is_extraction_query(self, query: str) -> bool:
        """Determine if a query is asking for content extraction."""
        extraction_keywords = [
            "extract",
            "scrape",
            "content of",
            "text from",
            "get content",
            "get information from",
            "website content",
            "page content",
        ]
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in extraction_keywords)

    def _extract_url_from_query(self, query: str) -> str | None:
        """Try to extract a URL from the query."""
        # Improved URL extraction
        words = query.split()
        for word in words:
            # Check for URLs with protocol
            if word.startswith(("http://", "https://")):
                return word

            # Check for common domain patterns
            if (word.startswith("www.") and "." in word[4:]) or (
                not word.startswith("www.")
                and "." in word
                and any(
                    word.endswith(tld)
                    for tld in [".com", ".org", ".net", ".edu", ".gov", ".io", ".co"]
                )
            ):
                # Add https:// prefix if missing
                if word.startswith("www."):
                    return "https://" + word
                return "https://" + word

        return None

    def get_capabilities(self) -> dict[str, Any]:
        """Return Firecrawl capabilities."""
        return {
            "content_types": ["web_content", "extraction", "general"],
            "features": {
                "content_extraction": True,
                "scraping": True,
                "deep_research": True,
                "url_discovery": True,
                "crawling": True,
                "structured_data_extraction": True,
                "llms_txt_generation": True,
            },
            "quality_metrics": {
                "extraction_quality": 0.95,
                "search_quality": 0.80,
                "crawling_speed": 0.90,
            },
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Firecrawl costs ~$0.02 per search
        # ~$0.05 per content extraction
        # ~$0.10 per deep research
        # ~$0.03 per URL discovery
        extraction_query = self._is_extraction_query(query.query)
        deep_research_query = (
            "research" in query.query.lower() or "analyze" in query.query.lower()
        )

        if deep_research_query:
            return 0.10
        if extraction_query:
            return 0.05
        return 0.02

    async def check_status(self) -> tuple[HealthStatus, str]:
        """Check the status of Firecrawl service."""
        try:
            # Make a simple API call to check if Firecrawl is responsive
            response = await self.client.get(
                "https://api.firecrawl.dev/v1/status",
                headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
            )

            if response.status_code == 200:
                return HealthStatus.OK, "Firecrawl API is operational"
            return (
                HealthStatus.DEGRADED,
                f"Firecrawl API returned status code {response.status_code}",
            )

        except httpx.RequestError as e:
            return HealthStatus.FAILED, f"Connection to Firecrawl API failed: {str(e)}"
        except Exception as e:
            return HealthStatus.FAILED, f"Firecrawl status check failed: {str(e)}"

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
