"""FastMCP search server implementation using unified router."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastmcp import Context, FastMCP
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import get_settings
from .middleware import (
    AuthMiddleware,
    ErrorHandlerMiddleware,
    LoggingMiddleware,
    MiddlewareManager,
    RateLimitMiddleware,
    RetryMiddleware,
)
from .models.base import HealthResponse, HealthStatus, MetricsResponse, ProviderStatus
from .models.query import SearchQuery
from .models.results import CombinedSearchResponse, SearchResponse
from .providers.base import SearchProvider
from .providers.exa_mcp import ExaMCPProvider
from .providers.firecrawl_mcp import FirecrawlMCPProvider
from .providers.linkup_mcp import LinkupMCPProvider
from .providers.perplexity_mcp import PerplexityMCPProvider
from .providers.tavily_mcp import TavilyMCPProvider
from .query_routing.analyzer import QueryAnalyzer
from .query_routing.router import SearchRouter
from .result_processing.merger import ResultMerger
from .utils.cache import SearchCache
from .utils.metrics import MetricsTracker

logger = logging.getLogger(__name__)


class SearchServer:
    """FastMCP search server implementation with unified routing and provider management."""

    def __init__(self) -> None:
        """Initialize the SearchServer with all components and providers."""
        # Initialize settings
        self.settings = get_settings()

        # Initialize middleware manager
        self.middleware_manager = MiddlewareManager()

        # Initialize FastMCP server
        self.mcp = FastMCP(
            name="MCP Search Hub",
            instructions="""
            This server provides access to multiple search providers through a unified interface.
            Use the search tool to find information with automatic provider selection.
            """,
            log_level=self.settings.log_level,
        )

        # Setup middleware
        self._setup_middleware()

        # Initialize providers directly
        self.providers = self._initialize_providers()
        logger.info(f"Initialized providers: {list(self.providers.keys())}")

        # Initialize components
        self.analyzer = QueryAnalyzer()

        # Initialize router
        self.router = SearchRouter(
            providers=self.providers,
            max_concurrent=self.settings.router.max_concurrent,
            default_timeout=self.settings.router.max_timeout_ms / 1000.0,  # Convert ms to seconds
            circuit_failure_threshold=self.settings.router.circuit_failure_threshold,
            circuit_recovery_timeout=self.settings.router.circuit_recovery_timeout,
        )

        self.merger = ResultMerger()

        # Initialize Redis cache
        self.cache = SearchCache(
            redis_url=self.settings.cache.redis_url,
            default_ttl=self.settings.cache.redis_ttl,
            ttl_jitter=self.settings.cache.ttl_jitter,
            prefix=self.settings.cache.prefix,
        )
        logger.info(
            f"Initialized SearchCache with Redis at {self.settings.cache.redis_url}"
        )

        self.metrics = MetricsTracker()

        # Register tools and custom routes
        self._register_tools()
        self._register_custom_routes()

        # Provider tools will be registered when the server starts
        self._provider_tools_registered = False

    def _setup_middleware(self):
        """Set up and configure middleware components."""
        # Get the Starlette app from FastMCP
        app = self.mcp.http_app

        # Add middleware directly to the Starlette app
        middleware_config = self.settings.middleware
        retry_config = self.settings.retry

        # Add middleware in reverse order (last added runs first)
        # Note: Retry middleware uses retry config from root level
        app.add_middleware(
            RetryMiddleware,
            max_retries=retry_config.max_retries,
            base_delay=retry_config.base_delay,
            max_delay=retry_config.max_delay,
            exponential_base=retry_config.exponential_base,
            jitter=retry_config.jitter,
            skip_paths=middleware_config.rate_limit_skip_paths,  # Using rate limit skip paths
        )
        logger.info("Retry middleware initialized")

        if middleware_config.rate_limit_enabled:
            app.add_middleware(
                RateLimitMiddleware,
                limit=middleware_config.rate_limit_requests,
                window=middleware_config.rate_limit_window,
                global_limit=middleware_config.rate_limit_global,
                global_window=middleware_config.rate_limit_window,
                skip_paths=middleware_config.rate_limit_skip_paths,
            )
            logger.info("Rate limit middleware initialized")

        if middleware_config.auth_enabled:
            app.add_middleware(
                AuthMiddleware,
                api_keys=middleware_config.auth_api_keys,
                skip_auth_paths=middleware_config.auth_skip_paths,
            )
            logger.info("Authentication middleware initialized")

        if middleware_config.logging_enabled:
            app.add_middleware(
                LoggingMiddleware,
                log_level=self.settings.log_level,
                include_headers=middleware_config.logging_include_headers,
                include_body=middleware_config.logging_include_body,
                sensitive_headers=middleware_config.logging_sensitive_headers,
                max_body_size=middleware_config.logging_max_body_size,
            )
            logger.info("Logging middleware initialized")

        # Error handler is always enabled
        app.add_middleware(
            ErrorHandlerMiddleware,
            include_traceback=self.settings.environment == "development",
            redact_sensitive_data=True,
        )
        logger.info("Error handler middleware initialized")

    def _initialize_providers(self) -> dict[str, SearchProvider]:
        """Initialize providers with direct imports."""
        settings = get_settings()
        providers = {}

        # Map of provider names to classes
        provider_classes = {
            "exa": ExaMCPProvider,
            "firecrawl": FirecrawlMCPProvider,
            "linkup": LinkupMCPProvider,
            "perplexity": PerplexityMCPProvider,
            "tavily": TavilyMCPProvider,
        }

        for provider_name, provider_class in provider_classes.items():
            # Get provider settings from new structure
            provider_settings = settings.get_provider_config(provider_name)
            if not provider_settings:
                logger.warning(f"No settings found for provider {provider_name}")
                continue

            # Skip disabled providers
            if not provider_settings.enabled:
                logger.info(f"Provider {provider_name} is disabled")
                continue

            # Get API key
            api_key = None
            if provider_settings.api_key:
                api_key = provider_settings.api_key.get_secret_value()

            # Create provider instance
            try:
                providers[provider_name] = provider_class(api_key=api_key)
                logger.info(f"Successfully initialized provider: {provider_name}")
            except Exception as e:
                logger.error(f"Failed to initialize provider {provider_name}: {e}")

        return providers

    def _register_tools(self):
        """Register search tools with FastMCP server."""

        @self.mcp.tool(
            name="search",
            description="Search across multiple providers with intelligent routing",
        )
        async def search(
            query: str,
            ctx: Context,
            max_results: int = 10,
            raw_content: bool = False,
            advanced: dict[str, Any] | None = None,
        ) -> SearchResponse:
            """Execute a search query across multiple providers."""
            request_id = str(uuid.uuid4())
            ctx.info(f"Processing search request {request_id}: {query}")

            # Build search query object
            search_query = SearchQuery(
                query=query,
                max_results=max_results,
                raw_content=raw_content,
                advanced=advanced,
            )

            # Use search_with_routing which handles caching internally
            response = await self.search_with_routing(search_query, request_id, ctx)
            return SearchResponse(results=response.results, metadata=response.metadata)

    async def _register_provider_tools(self):
        """Register provider-specific tools dynamically."""
        # Initialize all providers
        init_tasks = []
        for provider_name, provider in self.providers.items():
            try:
                init_tasks.append(provider.initialize())
            except Exception as e:
                logger.error(
                    f"Failed to create initialization task for {provider_name}: {e}"
                )

        # Wait for all initializations
        init_results = await asyncio.gather(*init_tasks, return_exceptions=True)

        # Log any initialization errors
        for provider_name, result in zip(
            self.providers.keys(), init_results, strict=False
        ):
            if isinstance(result, Exception):
                logger.error(f"Failed to initialize {provider_name}: {result}")

        # Register tools for successfully initialized providers
        for provider_name, provider in self.providers.items():
            if not provider.initialized:
                logger.warning(
                    f"Skipping tool registration for uninitialized provider: {provider_name}"
                )
                continue

            try:
                # Get provider's tools
                tools = await provider.list_tools()

                for tool in tools:
                    # Create a closure to capture the current values
                    def create_tool_wrapper(
                        prov_name: str, prov: SearchProvider, orig_tool_name: str, tool_desc: str
                    ):
                        @self.mcp.tool(
                            name=f"{prov_name}_{orig_tool_name}",
                            description=f"{tool_desc} (via {prov_name})",
                        )
                        async def provider_tool_wrapper(ctx: Context, **kwargs):
                            """Wrapper function for provider-specific tools."""
                            request_id = str(uuid.uuid4())
                            ctx.info(
                                f"Invoking {prov_name} tool {orig_tool_name} with request {request_id}"
                            )

                            try:
                                # Use the provider's invoke_tool method
                                return await prov.invoke_tool(orig_tool_name, kwargs)
                            except Exception as e:
                                ctx.error(
                                    f"Error invoking {prov_name} tool {orig_tool_name}: {str(e)}"
                                )
                                raise

                        return provider_tool_wrapper

                    # Register the tool
                    create_tool_wrapper(provider_name, provider, tool.name, tool.description)

                logger.info(
                    f"Registered {len(tools)} tools for provider {provider_name}"
                )

            except Exception as e:
                logger.error(f"Failed to register tools for {provider_name}: {e}")

    def _register_custom_routes(self):
        """Register custom FastMCP HTTP routes."""
        # Use http_app for custom routes
        app = self.mcp.http_app

        @app.post("/search/combined")
        async def search_combined(request: Request) -> JSONResponse:
            """Execute a combined search across multiple providers."""
            try:
                # Parse request body
                try:
                    data = await request.json()
                except json.JSONDecodeError as e:
                    return JSONResponse(
                        content={
                            "error": "Invalid JSON in request body",
                            "details": str(e),
                        },
                        status_code=400,
                    )

                # Validate query
                try:
                    search_query = SearchQuery(**data)
                except ValidationError as e:
                    return JSONResponse(
                        content={
                            "error": "Invalid search query parameters",
                            "details": e.errors(),
                        },
                        status_code=422,
                    )

                request_id = str(uuid.uuid4())

                # Create a simple context for logging
                class SimpleContext:
                    def info(self, msg):
                        logger.info(msg)

                    def warning(self, msg):
                        logger.warning(msg)

                    def error(self, msg):
                        logger.error(msg)

                ctx = SimpleContext()

                # Use search_with_routing
                try:
                    response = await self.search_with_routing(search_query, request_id, ctx)
                except TimeoutError:
                    return JSONResponse(
                        content={
                            "error": "Search request timed out",
                            "request_id": request_id,
                        },
                        status_code=504,
                    )
                except Exception as e:
                    # Check if it's a known provider error
                    if "rate limit" in str(e).lower():
                        return JSONResponse(
                            content={
                                "error": "Rate limit exceeded",
                                "details": str(e),
                                "request_id": request_id,
                            },
                            status_code=429,
                        )
                    if "budget" in str(e).lower():
                        return JSONResponse(
                            content={
                                "error": "Budget limit exceeded",
                                "details": str(e),
                                "request_id": request_id,
                            },
                            status_code=402,
                        )
                    raise

                return JSONResponse(content=response.model_dump(mode="json"))

            except Exception as e:
                logger.error(f"Error in search_combined: {str(e)}", exc_info=True)
                return JSONResponse(
                    content={
                        "error": "Internal server error",
                        "message": str(e),
                        "request_id": request_id if 'request_id' in locals() else None,
                    },
                    status_code=500,
                )

        @app.get("/health")
        async def health_check(request: Request) -> JSONResponse:
            """Health check endpoint."""
            # Build provider health status
            provider_health = {}
            for name, provider in self.providers.items():
                status = await provider.check_status()
                if status:
                    # Get rate limit and budget info
                    is_rate_limited = provider.rate_limiter.is_in_cooldown()
                    budget_info = provider.budget_tracker.get_usage_report()
                    budget_exceeded = budget_info.get("daily_percent_used", 0) >= 100

                    status_message = status[1]
                    health_status = status[0]

                    # Update health status based on rate limits and budget
                    if is_rate_limited:
                        status_message = f"{status_message} (RATE LIMITED)"
                        if health_status != HealthStatus.FAILED:
                            health_status = HealthStatus.DEGRADED

                    if budget_exceeded:
                        status_message = f"{status_message} (BUDGET EXCEEDED)"
                        if health_status != HealthStatus.FAILED:
                            health_status = HealthStatus.DEGRADED

                    provider_health[name] = ProviderStatus(
                        name=name,
                        health=health_status,
                        status=health_status != HealthStatus.FAILED,
                        message=status_message,
                        rate_limited=is_rate_limited,
                        budget_exceeded=budget_exceeded,
                    )
                else:
                    provider_health[name] = ProviderStatus(
                        name=name,
                        health=HealthStatus.UNHEALTHY,
                        status=False,
                        message="Provider unresponsive",
                    )

            # Overall health
            overall_health = HealthStatus.HEALTHY
            if all(
                p.health == HealthStatus.UNHEALTHY for p in provider_health.values()
            ):
                overall_health = HealthStatus.UNHEALTHY
            elif any(
                p.health in [HealthStatus.UNHEALTHY, HealthStatus.DEGRADED]
                for p in provider_health.values()
            ):
                overall_health = HealthStatus.DEGRADED

            response = HealthResponse(
                status=overall_health.value,
                healthy_providers=len(
                    [
                        p
                        for p in provider_health.values()
                        if p.health == HealthStatus.HEALTHY
                    ]
                ),
                total_providers=len(provider_health),
                providers=provider_health,
            )

            status_code = 200 if overall_health == HealthStatus.HEALTHY else 503
            return JSONResponse(
                content=response.model_dump(mode="json"), status_code=status_code
            )

        @app.get("/metrics")
        async def metrics(request: Request) -> JSONResponse:
            """Metrics endpoint."""
            # Get performance metrics
            metrics_data = self.metrics.get_metrics()

            # Build provider metrics
            provider_metrics = {}
            for name in self.providers:
                if name in metrics_data:
                    provider_metrics[name] = {
                        "queries": metrics_data[name].get("queries", 0),
                        "successes": metrics_data[name].get("successes", 0),
                        "failures": metrics_data[name].get("failures", 0),
                        "success_rate": metrics_data[name].get("success_rate", 0.0),
                        "avg_response_time": metrics_data[name].get(
                            "avg_response_time", 0.0
                        ),
                    }

            # Aggregate metrics
            total_queries = sum(m.get("queries", 0) for m in provider_metrics.values())
            total_successes = sum(
                m.get("successes", 0) for m in provider_metrics.values()
            )
            total_failures = sum(
                m.get("failures", 0) for m in provider_metrics.values()
            )

            response = MetricsResponse(
                total_queries=total_queries,
                total_successes=total_successes,
                total_failures=total_failures,
                cache_hit_rate=metrics_data.get("cache_hit_rate", 0.0),
                avg_response_time=metrics_data.get("avg_response_time", 0.0),
                provider_metrics=provider_metrics,
                last_updated=metrics_data.get("last_updated", time.time()),
            )

            return JSONResponse(content=response.model_dump(mode="json"))

    async def search_with_routing(
        self, search_query: SearchQuery, request_id: str, ctx: Context
    ) -> CombinedSearchResponse:
        """Execute a search using the unified router."""
        # Check cache
        cached_result = await self.cache.get(search_query)

        if cached_result:
            ctx.info(f"Cache hit for request {request_id}")
            # Track cache hit metric
            self.metrics.record_query(
                provider_name="_cache",
                success=True,
                response_time=0.001,
                result_count=len(cached_result.results),
            )
            return cached_result

        # Analyze query
        features = self.analyzer.analyze(search_query)
        ctx.info(f"Request {request_id} - Query features: {features.model_dump()}")

        # Route and execute
        ctx.info(f"Request {request_id} - Starting search with router")
        start_time = time.time()

        # Use the router which handles provider selection and execution
        results = await self.router.route_and_execute(
            query=search_query,
            features=features,
            max_providers=3,
        )

        response_time = time.time() - start_time
        ctx.info(f"Request {request_id} - Search completed in {response_time:.2f}s")

        # Merge results from all providers
        merged_results = self.merger.merge_results(results)

        # Build combined response
        response = CombinedSearchResponse(
            results=merged_results,
            metadata={
                "request_id": request_id,
                "query": search_query.query,
                "features": features.model_dump(),
                "providers_used": list(results.keys()),
                "result_count": len(merged_results),
                "response_time": response_time,
            },
        )

        # Cache the response
        await self.cache.set(search_query, response)

        # Track metrics for actual providers used
        for provider_name in results:
            provider_results = results[provider_name]
            self.metrics.record_query(
                provider_name=provider_name,
                success=len(provider_results) > 0,
                response_time=response_time
                / len(results),  # Approximate per-provider time
                result_count=len(provider_results),
            )

        return response

    async def start(
        self,
        transport: str = "streamable-http",
        host: str = "0.0.0.0",
        port: int = 8000,
    ):
        """Start the FastMCP server."""
        # Initialize all providers and register their tools
        if not self._provider_tools_registered:
            logger.info("Initializing providers and registering tools...")
            await self._register_provider_tools()
            self._provider_tools_registered = True

        # Run the server based on transport
        logger.info(
            f"Starting MCP Search Hub on {host}:{port} with transport {transport}"
        )

        if transport == "stdio":
            await self.mcp.run_stdio_async()
        elif transport == "streamable-http":
            await self.mcp.run_streamable_http_async(host=host, port=port)
        else:
            # Default HTTP
            await self.mcp.run_http_async(host=host, port=port)

    def run(
        self,
        transport: str = "streamable-http",
        host: str = "0.0.0.0",
        port: int = 8000,
        log_level: str = "INFO",
    ):
        """Run the server synchronously."""
        asyncio.run(self.start(transport=transport, host=host, port=port))

    async def close(self):
        """Close all providers and cleanup resources."""
        logger.info("Closing all providers...")
        close_tasks = []

        for provider_name, provider in self.providers.items():
            if provider.initialized:
                try:
                    close_tasks.append(provider.close())
                except Exception as e:
                    logger.error(
                        f"Failed to create close task for {provider_name}: {e}"
                    )

        # Wait for all providers to close
        if close_tasks:
            close_results = await asyncio.gather(*close_tasks, return_exceptions=True)

            # Log any close errors
            for provider_name, result in zip(
                self.providers.keys(), close_results, strict=False
            ):
                if isinstance(result, Exception):
                    logger.error(f"Failed to close {provider_name}: {result}")

        # Close cache
        try:
            await self.cache.close()
            logger.info("Closed cache connections")
        except Exception as e:
            logger.error(f"Failed to close cache connections: {e}")

        logger.info("All resources closed")
