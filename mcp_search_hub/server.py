"""FastMCP search server implementation."""

import asyncio
import time
import uuid

from fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import get_settings
from .models.base import HealthResponse, HealthStatus, MetricsResponse, ProviderStatus
from .models.query import SearchQuery
from .models.results import CombinedSearchResponse, SearchResponse
from .providers.base import SearchProvider
from .providers.exa_mcp import ExaProvider
from .providers.firecrawl_mcp import FirecrawlProvider
from .providers.linkup_mcp import LinkupProvider
from .providers.perplexity_mcp import PerplexityProvider
from .providers.tavily_mcp import TavilyProvider
from .query_routing.analyzer import QueryAnalyzer
from .query_routing.router import QueryRouter
from .result_processing.merger import ResultMerger
from .utils.cache import QueryCache
from .utils.metrics import MetricsTracker


class SearchServer:
    """FastMCP search server implementation."""

    def __init__(self):
        # Initialize FastMCP server
        self.mcp = FastMCP(
            name="MCP Search Hub",
            instructions="""
            This server provides access to multiple search providers through a unified interface.
            Use the search tool to find information with automatic provider selection.
            """,
            log_level=get_settings().log_level,
        )

        # Initialize providers
        settings = get_settings()
        self.providers: dict[str, SearchProvider] = {
            "linkup": LinkupProvider(
                {
                    "linkup_api_key": (
                        settings.providers.linkup.api_key.get_secret_value()
                        if settings.providers.linkup.api_key
                        else None
                    )
                }
            ),
            "exa": ExaProvider(
                {"exa_api_key": settings.providers.exa.api_key.get_secret_value()}
            ),
            "perplexity": PerplexityProvider(
                {
                    "perplexity_api_key": settings.providers.perplexity.api_key.get_secret_value()
                }
            ),
            "tavily": TavilyProvider(
                {
                    "tavily_api_key": (
                        settings.providers.tavily.api_key.get_secret_value()
                        if settings.providers.tavily.api_key
                        else None
                    )
                }
            ),
            "firecrawl": FirecrawlProvider(),
        }

        # Initialize components
        self.analyzer = QueryAnalyzer()
        self.router = QueryRouter(self.providers)
        self.merger = ResultMerger()
        self.cache = QueryCache(ttl=get_settings().cache_ttl)
        self.metrics = MetricsTracker()

        # Register tools and custom routes
        self._register_tools()
        self._register_custom_routes()

    def _register_custom_routes(self):
        """Register custom HTTP routes."""

        @self.mcp.custom_route("/health", methods=["GET"])
        async def health_check(request: Request) -> JSONResponse:
            """Health check endpoint."""
            providers_status = {}
            overall_status = HealthStatus.OK

            # Check each provider
            provider_tasks = []
            for name, provider in self.providers.items():
                if getattr(get_settings().providers, name).enabled:
                    provider_tasks.append(
                        (name, asyncio.create_task(provider.check_status()))
                    )

            # Wait for all provider checks
            for name, task in provider_tasks:
                try:
                    status, message = await task
                    providers_status[name] = ProviderStatus(
                        name=name, status=status, message=message
                    )

                    # Update overall status based on provider status
                    if status == HealthStatus.FAILED:
                        overall_status = HealthStatus.DEGRADED
                except Exception as e:
                    providers_status[name] = ProviderStatus(
                        name=name,
                        status=HealthStatus.FAILED,
                        message=f"Check failed: {str(e)}",
                    )
                    overall_status = HealthStatus.DEGRADED

            # Return health response
            response = HealthResponse(
                status=overall_status, version="1.0.0", providers=providers_status
            )

            return JSONResponse(response.model_dump())

        @self.mcp.custom_route("/metrics", methods=["GET"])
        async def metrics(request: Request) -> JSONResponse:
            """Metrics endpoint."""
            metrics_data = self.metrics.get_metrics()
            response = MetricsResponse(
                metrics=metrics_data, since=self.metrics.get_start_time_iso()
            )

            return JSONResponse(response.model_dump())

    def _register_tools(self):
        """Register FastMCP tools."""

        @self.mcp.tool()
        async def search(query: SearchQuery, ctx: Context) -> CombinedSearchResponse:
            """
            Search across multiple providers with automatic selection.

            The system automatically selects the best provider(s) for your query based on
            content type, complexity, and other factors.
            """
            # Generate a unique request ID and record metrics
            request_id = str(uuid.uuid4())
            self.metrics.start_request(request_id)

            start_time = time.time()

            # Check cache
            cache_key = f"{query.query}:{query.advanced}:{query.max_results}:{query.raw_content}"
            cached_result = self.cache.get(cache_key)
            if (
                cached_result and not query.providers
            ):  # Skip cache if explicit providers
                await ctx.info("Retrieved results from cache")
                # Record cache hit
                self.metrics.record_query(
                    set(cached_result.providers_used), from_cache=True
                )
                self.metrics.end_request(request_id)
                return cached_result

            # Extract features
            await ctx.info("Analyzing query")
            features = self.analyzer.extract_features(query)

            # Select providers (use explicit selection if provided)
            providers_to_use = query.providers or self.router.select_providers(
                query, features, query.budget
            )

            await ctx.info(f"Selected providers: {', '.join(providers_to_use)}")

            # Execute search with selected providers
            provider_tasks = {}
            for provider_name in providers_to_use:
                if provider_name in self.providers:
                    provider = self.providers[provider_name]
                    provider_tasks[provider_name] = asyncio.create_task(
                        provider.search(query)
                    )

            # Wait for all searches to complete with timeout
            timeout_sec = query.timeout_ms / 1000
            try:
                done, pending = await asyncio.wait(
                    provider_tasks.values(), timeout=timeout_sec
                )

                # Cancel any pending tasks
                for task in pending:
                    task.cancel()

                # Collect results
                provider_results = {}
                successful_providers = set()
                for provider_name, task in provider_tasks.items():
                    if task in done and not task.exception():
                        provider_results[provider_name] = task.result()
                        successful_providers.add(provider_name)
                    else:
                        # Handle errors or timeouts
                        if task.exception():
                            await ctx.error(
                                f"Provider {provider_name} error: {str(task.exception())}"
                            )
                            self.metrics.record_error()
                        else:
                            await ctx.warn(f"Provider {provider_name} timed out")
                            self.metrics.record_error()

                        # Create empty response for failed providers
                        provider_results[provider_name] = SearchResponse(
                            results=[],
                            query=query.query,
                            total_results=0,
                            provider=provider_name,
                            error="Timeout or error",
                        )

                # Merge and rank results
                combined_results = self.merger.merge_results(
                    provider_results,
                    max_results=query.max_results,
                    raw_content=query.raw_content,
                )

                # Calculate costs
                total_cost = sum(
                    self.providers[name].estimate_cost(query)
                    for name in provider_results
                )

                # Create response
                response = CombinedSearchResponse(
                    results=combined_results,
                    query=query.query,
                    providers_used=list(provider_results.keys()),
                    total_results=len(combined_results),
                    total_cost=total_cost,
                    timing_ms=(time.time() - start_time) * 1000,
                )

                # Cache the response
                self.cache.set(cache_key, response)

                # Record metrics
                self.metrics.record_query(successful_providers, from_cache=False)
                self.metrics.end_request(request_id)

                return response

            except Exception as e:
                await ctx.error(f"Search error: {str(e)}")
                # Record error
                self.metrics.record_error()
                self.metrics.end_request(request_id)

                # Return error response
                return CombinedSearchResponse(
                    results=[],
                    query=query.query,
                    providers_used=[],
                    total_results=0,
                    total_cost=0.0,
                    timing_ms=(time.time() - start_time) * 1000,
                )

        @self.mcp.tool()
        def get_provider_info() -> dict[str, dict]:
            """Get information about available search providers."""
            provider_info = {}

            for name, provider in self.providers.items():
                provider_info[name] = provider.get_capabilities()

            return provider_info

        # Register Firecrawl tools
        firecrawl_provider = self.providers.get("firecrawl")
        if firecrawl_provider and isinstance(firecrawl_provider, FirecrawlProvider):

            @self.mcp.tool()
            async def firecrawl_scrape(
                url: str,
                formats: list[str] = ["markdown"],
                onlyMainContent: bool = True,
                timeout: int = 30000,
                **kwargs,
            ) -> dict:
                """
                Scrape a single webpage with Firecrawl.

                Args:
                    url: The URL to scrape
                    formats: Content formats to extract (markdown, html, rawHtml, screenshot, links)
                    onlyMainContent: Extract only the main content
                    timeout: Maximum time to wait for page load
                """
                return await firecrawl_provider.scrape_url(
                    url,
                    formats=formats,
                    onlyMainContent=onlyMainContent,
                    timeout=timeout,
                    **kwargs,
                )

            @self.mcp.tool()
            async def firecrawl_map(
                url: str,
                search: str = None,
                ignoreSubdomains: bool = False,
                limit: int = None,
            ) -> dict:
                """
                Discover URLs from a starting point using sitemap and crawling.

                Args:
                    url: Starting URL for URL discovery
                    search: Optional search term to filter URLs
                    ignoreSubdomains: Skip subdomains
                    limit: Maximum number of URLs to return
                """
                return await firecrawl_provider.firecrawl_map(
                    url, search=search, ignoreSubdomains=ignoreSubdomains, limit=limit
                )

            @self.mcp.tool()
            async def firecrawl_crawl(
                url: str, limit: int = 10, maxDepth: int = 3, **options
            ) -> dict:
                """
                Start an asynchronous crawl of multiple pages.

                Args:
                    url: Starting URL for the crawl
                    limit: Maximum number of pages to crawl
                    maxDepth: Maximum link depth to crawl
                """
                return await firecrawl_provider.firecrawl_crawl(
                    url, limit=limit, maxDepth=maxDepth, **options
                )

            @self.mcp.tool()
            async def firecrawl_check_crawl_status(id: str) -> dict:
                """
                Check the status of a crawl job.

                Args:
                    id: The crawl job ID
                """
                return await firecrawl_provider.firecrawl_check_crawl_status(id)

            @self.mcp.tool()
            async def firecrawl_search(query: str, limit: int = 5, **options) -> dict:
                """
                Search the web with Firecrawl.

                Args:
                    query: Search query string
                    limit: Maximum number of results
                """
                return await firecrawl_provider.firecrawl_search(
                    query, limit=limit, **options
                )

            @self.mcp.tool()
            async def firecrawl_extract(
                urls: list[str], prompt: str, systemPrompt: str = None
            ) -> dict:
                """
                Extract structured information from web pages using LLM.

                Args:
                    urls: List of URLs to extract information from
                    prompt: Prompt for the LLM extraction
                    systemPrompt: System prompt for LLM extraction
                """
                return await firecrawl_provider.firecrawl_extract(
                    urls, prompt=prompt, systemPrompt=systemPrompt
                )

            @self.mcp.tool()
            async def firecrawl_deep_research(
                query: str, maxDepth: int = 3, maxUrls: int = 100, timeLimit: int = 300
            ) -> dict:
                """
                Conduct deep research on a query using web crawling and AI analysis.

                Args:
                    query: The query to research
                    maxDepth: Maximum depth of research iterations
                    maxUrls: Maximum number of URLs to analyze
                    timeLimit: Time limit in seconds
                """
                return await firecrawl_provider.firecrawl_deep_research(
                    query, maxDepth=maxDepth, maxUrls=maxUrls, timeLimit=timeLimit
                )

            @self.mcp.tool()
            async def firecrawl_generate_llmstxt(
                url: str, maxUrls: int = 10, showFullText: bool = False
            ) -> dict:
                """
                Generate standardized LLMs.txt file for a URL.

                Args:
                    url: The URL to generate LLMs.txt from
                    maxUrls: Maximum number of URLs to process
                    showFullText: Whether to show the full LLMs-full.txt
                """
                return await firecrawl_provider.firecrawl_generate_llmstxt(
                    url, maxUrls=maxUrls, showFullText=showFullText
                )

        # Register Exa tools
        exa_provider = self.providers.get("exa")
        if exa_provider and isinstance(exa_provider, ExaProvider):

            @self.mcp.tool()
            async def exa_search(
                query: str,
                limit: int = 10,
                type: str = "neural",
                **kwargs,
            ) -> dict:
                """
                Search the web using Exa's semantic search engine.

                Args:
                    query: Search query string
                    limit: Maximum number of results (default: 10)
                    type: Search type ('neural', 'keyword', 'hybrid')
                """
                return await exa_provider.mcp_wrapper.invoke_tool(
                    "web_search_exa",
                    {"query": query, "limit": limit, "type": type, **kwargs},
                )

            @self.mcp.tool()
            async def exa_research_papers(
                query: str,
                limit: int = 10,
                **kwargs,
            ) -> dict:
                """
                Search for research papers using Exa.

                Args:
                    query: Search query for research papers
                    limit: Maximum number of results
                """
                return await exa_provider.research_papers(query, limit=limit, **kwargs)

            @self.mcp.tool()
            async def exa_company_research(
                query: str,
                **kwargs,
            ) -> dict:
                """
                Research companies using Exa.

                Args:
                    query: Company or industry to research
                """
                return await exa_provider.company_research(query, **kwargs)

            @self.mcp.tool()
            async def exa_competitor_finder(
                company: str,
                **kwargs,
            ) -> dict:
                """
                Find competitors for a company using Exa.

                Args:
                    company: Company name to find competitors for
                """
                return await exa_provider.competitor_finder(company, **kwargs)

            @self.mcp.tool()
            async def exa_linkedin_search(
                query: str,
                limit: int = 10,
                **kwargs,
            ) -> dict:
                """
                Search LinkedIn using Exa.

                Args:
                    query: LinkedIn search query
                    limit: Maximum number of results
                """
                return await exa_provider.linkedin_search(query, limit=limit, **kwargs)

            @self.mcp.tool()
            async def exa_wikipedia_search(
                query: str,
                limit: int = 10,
                **kwargs,
            ) -> dict:
                """
                Search Wikipedia using Exa.

                Args:
                    query: Wikipedia search query
                    limit: Maximum number of results
                """
                return await exa_provider.wikipedia_search(query, limit=limit, **kwargs)

            @self.mcp.tool()
            async def exa_github_search(
                query: str,
                limit: int = 10,
                **kwargs,
            ) -> dict:
                """
                Search GitHub using Exa.

                Args:
                    query: GitHub search query
                    limit: Maximum number of results
                """
                return await exa_provider.github_search(query, limit=limit, **kwargs)

            @self.mcp.tool()
            async def exa_crawl(
                url: str,
                **kwargs,
            ) -> dict:
                """
                Crawl a URL using Exa.

                Args:
                    url: URL to crawl and extract content from
                """
                return await exa_provider.crawl(url, **kwargs)

        # Register Perplexity tools
        perplexity_provider = self.providers.get("perplexity")
        if perplexity_provider and isinstance(perplexity_provider, PerplexityProvider):

            @self.mcp.tool()
            async def perplexity_ask(
                query: str,
                search_focus: str = "web",
                **kwargs,
            ) -> dict:
                """
                Ask Perplexity a question with web search capabilities.

                Args:
                    query: The question to ask
                    search_focus: Search focus type ('web', 'academic', 'youtube', etc.)
                """
                return await perplexity_provider.mcp_wrapper.call_tool(
                    "perplexity_ask",
                    {
                        "messages": [{"role": "user", "content": query}],
                        "search_focus": search_focus,
                        **kwargs,
                    },
                )

            @self.mcp.tool()
            async def perplexity_research(
                query: str,
                **kwargs,
            ) -> dict:
                """
                Conduct deep research on a topic using Perplexity.

                Args:
                    query: The topic to research
                """
                return await perplexity_provider.perplexity_research(query, **kwargs)

            @self.mcp.tool()
            async def perplexity_reason(
                query: str,
                **kwargs,
            ) -> dict:
                """
                Perform reasoning tasks using Perplexity.

                Args:
                    query: The reasoning task or question
                """
                return await perplexity_provider.perplexity_reason(query, **kwargs)

        # Register Linkup tools
        linkup_provider = self.providers.get("linkup")
        if linkup_provider and isinstance(linkup_provider, LinkupProvider):

            @self.mcp.tool()
            async def linkup_search_web(
                query: str,
                depth: str = "standard",
                **kwargs,
            ) -> dict:
                """
                Search the web using Linkup for real-time information and premium content.

                Args:
                    query: The search query to perform
                    depth: Search depth ('standard' or 'deep')
                """
                return await linkup_provider.mcp_wrapper.call_tool(
                    "search-web",
                    {"query": query, "depth": depth, **kwargs},
                )

        # Register Tavily tools
        tavily_provider = self.providers.get("tavily")
        if tavily_provider and isinstance(tavily_provider, TavilyProvider):

            @self.mcp.tool()
            async def tavily_search(
                query: str,
                search_depth: str = "basic",
                max_results: int = 5,
                **kwargs,
            ) -> dict:
                """
                Search the web using Tavily's AI-optimized search.

                Args:
                    query: Search query string
                    search_depth: Search depth ('basic' or 'advanced')
                    max_results: Maximum number of results (default: 5)
                """
                return await tavily_provider.mcp_wrapper.call_tool(
                    "tavily-search",
                    {
                        "query": query,
                        "options": {
                            "searchDepth": search_depth,
                            "maxResults": max_results,
                            **kwargs,
                        },
                    },
                )

            @self.mcp.tool()
            async def tavily_extract(
                url: str,
                extract_depth: str = "advanced",
                **kwargs,
            ) -> dict:
                """
                Extract and analyze content from a URL using Tavily.

                Args:
                    url: URL to extract content from
                    extract_depth: Extraction depth ('basic' or 'advanced')
                """
                return await tavily_provider.mcp_wrapper.call_tool(
                    "tavily-extract",
                    {
                        "urls": [url],
                        "options": {"extractDepth": extract_depth, **kwargs},
                    },
                )

    async def close(self):
        """Close all provider connections."""
        close_tasks = []
        for provider in self.providers.values():
            if hasattr(provider, "close"):
                close_tasks.append(asyncio.create_task(provider.close()))

        if close_tasks:
            await asyncio.gather(*close_tasks)

    def run(self, **kwargs):
        """Run the FastMCP server."""
        self.mcp.run(**kwargs)
