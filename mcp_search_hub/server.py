"""FastMCP search server implementation using unified router."""

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
from .models.router import TimeoutConfig
from .providers.base import SearchProvider
from .providers.exa_mcp import ExaMCPProvider
from .providers.firecrawl_mcp import FirecrawlMCPProvider
from .providers.linkup_mcp import LinkupMCPProvider
from .providers.perplexity_mcp import PerplexityMCPProvider
from .providers.tavily_mcp import TavilyMCPProvider
from .query_routing.analyzer import QueryAnalyzer
from .query_routing.unified_router import UnifiedRouter
from .result_processing.merger import ResultMerger
from .utils.cache import QueryCache
from .utils.metrics import MetricsTracker


class SearchServer:
    """FastMCP search server implementation with unified routing."""

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
            "linkup": LinkupMCPProvider(
                api_key=(
                    settings.providers.linkup.api_key.get_secret_value()
                    if settings.providers.linkup.api_key
                    else None
                )
            ),
            "exa": ExaMCPProvider(
                api_key=(
                    settings.providers.exa.api_key.get_secret_value()
                    if settings.providers.exa.api_key
                    else None
                )
            ),
            "perplexity": PerplexityMCPProvider(
                api_key=(
                    settings.providers.perplexity.api_key.get_secret_value()
                    if settings.providers.perplexity.api_key
                    else None
                )
            ),
            "tavily": TavilyMCPProvider(
                api_key=(
                    settings.providers.tavily.api_key.get_secret_value()
                    if settings.providers.tavily.api_key
                    else None
                )
            ),
            "firecrawl": FirecrawlMCPProvider(
                api_key=(
                    settings.providers.firecrawl.api_key.get_secret_value()
                    if settings.providers.firecrawl.api_key
                    else None
                )
            ),
        }

        # Initialize components
        self.analyzer = QueryAnalyzer()

        # Initialize UNIFIED router with timeout configuration
        timeout_config = TimeoutConfig()
        self.router = UnifiedRouter(
            providers=self.providers,
            timeout_config=timeout_config,
        )

        self.merger = ResultMerger()
        self.cache = QueryCache(ttl=get_settings().cache_ttl)
        self.metrics = MetricsTracker()

        # Register tools and custom routes
        self._register_tools()
        self._register_custom_routes()

    def _register_custom_routes(self) -> None:
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

    def _register_tools(self) -> None:
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

            # UNIFIED ROUTING: Route and execute in one step
            # Determine strategy based on query (if not specified in advanced settings)
            strategy = None
            if query.advanced and query.advanced.get("execution_strategy"):
                strategy = query.advanced.get("execution_strategy")

            # Use unified router to select providers and execute
            if query.providers:
                # If explicit providers specified, route to them
                routing_decision = self.router.select_providers(
                    query, features, query.budget
                )
                providers_to_use = query.providers
                await ctx.info(
                    f"Using explicit providers: {', '.join(providers_to_use)}"
                )
            else:
                # Auto-select providers
                routing_decision = self.router.select_providers(
                    query, features, query.budget
                )
                providers_to_use = routing_decision.selected_providers
                await ctx.info(f"Routing confidence: {routing_decision.confidence:.2f}")
                await ctx.info(f"Selected providers: {', '.join(providers_to_use)}")

            # Execute search with unified router
            try:
                execution_results = await self.router.route_and_execute(
                    query=query,
                    features=features,
                    budget=query.budget,
                    strategy=strategy,
                )

                # Convert execution results to provider results format
                provider_results = {}
                successful_providers = set()

                for provider_name, result in execution_results.items():
                    if result.success and result.response:
                        provider_results[provider_name] = result.response
                        successful_providers.add(provider_name)
                    else:
                        # Create empty response for failed providers
                        provider_results[provider_name] = SearchResponse(
                            results=[],
                            query=query.query,
                            total_results=0,
                            provider=provider_name,
                            error=result.error or "Failed",
                            timing_ms=result.duration_ms,
                        )

                # Log execution details
                await ctx.info(
                    f"Execution complete: {len(successful_providers)} providers succeeded"
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
                    for name in successful_providers
                    if name in self.providers
                )

                # Create response
                response = CombinedSearchResponse(
                    results=combined_results[: query.max_results],
                    total_results=len(combined_results),
                    query=query.query,
                    providers_used=list(successful_providers),
                    timing={"total_ms": int((time.time() - start_time) * 1000)},
                    cost={"total": total_cost},
                    error=(
                        "Some providers failed"
                        if len(successful_providers) < len(providers_to_use)
                        else None
                    ),
                )

                # Cache successful results
                if successful_providers and not query.providers:
                    self.cache.set(cache_key, response)

                # Record metrics
                await ctx.info(f"Search completed in {response.timing['total_ms']}ms")
                self.metrics.record_query(successful_providers)
                self.metrics.end_request(request_id)

                return response

            except Exception as e:
                # Handle unexpected errors
                await ctx.error(f"Error during search: {str(e)}")
                self.metrics.record_error()
                self.metrics.end_request(request_id)

                return CombinedSearchResponse(
                    results=[],
                    total_results=0,
                    query=query.query,
                    providers_used=[],
                    timing={"total_ms": int((time.time() - start_time) * 1000)},
                    cost={"total": 0.0},
                    error=str(e),
                )

        # Register provider-specific tools
        exa_provider = self.providers.get("exa")
        if exa_provider and isinstance(exa_provider, ExaMCPProvider):

            @self.mcp.tool()
            async def exa_research_papers(query: str, num_results: int = 5) -> dict:
                """
                Search for academic research papers using Exa.

                Args:
                    query: The search query for research papers
                    num_results: Number of results to return (default: 5)
                """
                return await exa_provider.research_papers(query, num_results)

            @self.mcp.tool()
            async def exa_company_research(company: str, num_results: int = 5) -> dict:
                """
                Research a specific company using Exa.

                Args:
                    company: The company name to research
                    num_results: Number of results to return (default: 5)
                """
                return await exa_provider.company_research(company, num_results)

        # Firecrawl provider tools
        firecrawl_provider = self.providers.get("firecrawl")
        if firecrawl_provider and isinstance(firecrawl_provider, FirecrawlMCPProvider):

            @self.mcp.tool()
            async def firecrawl_scrape(
                url: str,
                formats: list[str] = None,
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
                if formats is None:
                    formats = ["markdown"]
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
            async def firecrawl_crawl(url: str, **kwargs) -> dict:
                """
                Start an asynchronous crawl of multiple pages.

                Args:
                    url: Starting URL for the crawl
                    **kwargs: Additional crawl parameters (includePaths, excludePaths, maxDepth, etc.)
                """
                return await firecrawl_provider.firecrawl_crawl(url, **kwargs)

            @self.mcp.tool()
            async def firecrawl_extract(
                urls: list[str], prompt: str = None, schema: dict = None
            ) -> dict:
                """
                Extract structured information from web pages using LLM.

                Args:
                    urls: List of URLs to extract from
                    prompt: Prompt for the LLM extraction
                    schema: JSON schema for structured extraction
                """
                return await firecrawl_provider.firecrawl_extract(
                    urls, prompt=prompt, schema=schema
                )

            @self.mcp.tool()
            async def firecrawl_deep_research(
                query: str, timeLimit: int = 30, maxUrls: int = 10
            ) -> dict:
                """
                Conduct deep research on a query using web crawling and AI analysis.

                Args:
                    query: The research query
                    timeLimit: Time limit in seconds (default: 30)
                    maxUrls: Maximum URLs to analyze (default: 10)
                """
                return await firecrawl_provider.firecrawl_deep_research(
                    query, timeLimit=timeLimit, maxUrls=maxUrls
                )

        # Linkup provider tools
        linkup_provider = self.providers.get("linkup")
        if linkup_provider and isinstance(linkup_provider, LinkupMCPProvider):

            @self.mcp.tool()
            async def linkup_search_web(query: str, depth: str = "standard") -> dict:
                """
                Perform a web search using Linkup with specified depth.

                Args:
                    query: The search query
                    depth: Search depth - 'standard' or 'deep' (default: 'standard')
                """
                return await linkup_provider.search_web(query, depth)

        # Perplexity provider tools
        perplexity_provider = self.providers.get("perplexity")
        if perplexity_provider and isinstance(
            perplexity_provider, PerplexityMCPProvider
        ):

            @self.mcp.tool()
            async def perplexity_ask(messages: list[dict]) -> dict:
                """
                Engages in a conversation using the Perplexity Sonar API.

                Args:
                    messages: Array of conversation messages with role and content
                """
                return await perplexity_provider.ask(messages)

            @self.mcp.tool()
            async def perplexity_research(messages: list[dict]) -> dict:
                """
                Performs deep research using the Perplexity API.

                Args:
                    messages: Array of conversation messages with role and content
                """
                return await perplexity_provider.research(messages)

            @self.mcp.tool()
            async def perplexity_reason(messages: list[dict]) -> dict:
                """
                Performs reasoning tasks using the Perplexity API.

                Args:
                    messages: Array of conversation messages with role and content
                """
                return await perplexity_provider.reason(messages)

        # Tavily provider tools
        tavily_provider = self.providers.get("tavily")
        if tavily_provider and isinstance(tavily_provider, TavilyMCPProvider):

            @self.mcp.tool()
            async def tavily_search(
                query: str,
                search_depth: str = "basic",
                max_results: int = 10,
                include_raw_content: bool = False,
                topic: str = "general",
                **kwargs,
            ) -> dict:
                """
                Search the web using Tavily's AI search engine.

                Args:
                    query: Search query
                    search_depth: 'basic' or 'advanced' (default: 'basic')
                    max_results: Maximum results to return (default: 10)
                    include_raw_content: Include cleaned HTML content (default: False)
                    topic: Search topic - 'general' or 'news' (default: 'general')
                """
                return await tavily_provider.search(
                    query=query,
                    search_depth=search_depth,
                    max_results=max_results,
                    include_raw_content=include_raw_content,
                    topic=topic,
                    **kwargs,
                )

            @self.mcp.tool()
            async def tavily_extract(
                urls: list[str], extract_depth: str = "basic", **kwargs
            ) -> dict:
                """
                Extract content from URLs using Tavily.

                Args:
                    urls: List of URLs to extract content from
                    extract_depth: 'basic' or 'advanced' (default: 'basic')
                """
                return await tavily_provider.extract(
                    urls=urls, extract_depth=extract_depth, **kwargs
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
