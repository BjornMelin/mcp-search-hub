"""FastMCP search server implementation using unified router.

This module provides the core SearchServer class that orchestrates the entire
MCP Search Hub system. It integrates multiple search providers through a unified
interface, handles middleware, manages caching, and provides health monitoring.

The server supports both HTTP and stdio transports and includes comprehensive
middleware for authentication, rate limiting, logging, and error handling.

Example:
    Basic server initialization:
        >>> server = SearchServer()
        >>> server.run(transport="streamable-http", host="0.0.0.0", port=8000)

    Server with custom settings:
        >>> server = SearchServer()
        >>> # Server automatically uses configuration from environment
        >>> server.run()
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from fastmcp import Context, FastMCP
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

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
from .models.router import TimeoutConfig
from .providers.base import SearchProvider
from .providers.provider_config import PROVIDER_CONFIGS
from .query_routing.analyzer import QueryAnalyzer
from .query_routing.unified_router import UnifiedRouter
from .result_processing.merger import ResultMerger
from .utils.cache import QueryCache, TieredCache
from .utils.metrics import MetricsTracker

logger = logging.getLogger(__name__)


class MiddlewareHTTPWrapper(BaseHTTPMiddleware):
    """HTTP middleware wrapper that integrates the middleware manager with Starlette.

    This class bridges the gap between Starlette's HTTP middleware system and
    our custom middleware manager, allowing the middleware manager to process
    HTTP requests within the Starlette application framework.

    Attributes:
        middleware_manager: The MiddlewareManager instance that handles request processing
    """

    def __init__(self, app: Starlette, middleware_manager: MiddlewareManager) -> None:
        """Initialize the wrapper with the Starlette app and middleware manager.

        Args:
            app: The Starlette application instance
            middleware_manager: The middleware manager that will process requests
        """
        super().__init__(app)
        self.middleware_manager = middleware_manager

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process HTTP request through the middleware manager.

        This method is called for every HTTP request and delegates processing
        to the middleware manager, which applies all configured middleware
        in the correct order.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or handler in the chain

        Returns:
            The HTTP response after processing through all middleware
        """
        return await self.middleware_manager.process_http_request(request, call_next)


class SearchServer:
    """FastMCP search server implementation with unified routing and provider management.

    The SearchServer is the central orchestrator for the MCP Search Hub system. It manages:
    - Multiple search providers (Exa, Tavily, Linkup, Perplexity, Firecrawl)
    - Intelligent query routing and provider selection
    - Comprehensive middleware stack (auth, rate limiting, logging, etc.)
    - Caching system (memory and Redis tiers)
    - Health monitoring and metrics
    - Tool registration for MCP clients

    The server supports both HTTP and stdio transports and automatically discovers
    and initializes available search providers based on configuration.

    Attributes:
        settings: Server configuration settings
        middleware_manager: Manages the middleware processing pipeline
        mcp: FastMCP server instance
        providers: Dictionary of initialized search providers
        analyzer: Query analysis component
        router: Unified router for provider selection and execution
        merger: Result merging and ranking component
        cache: Caching system (QueryCache or TieredCache)
        metrics: Metrics tracking component

    Example:
        >>> server = SearchServer()
        >>> server.run(transport="streamable-http", host="0.0.0.0", port=8000)

        >>> # For stdio transport (MCP clients)
        >>> server = SearchServer()
        >>> server.run(transport="stdio")
    """

    def __init__(self) -> None:
        """Initialize the SearchServer with all components and providers.

        This method performs a complete initialization sequence:
        1. Loads configuration settings from environment
        2. Sets up the middleware processing pipeline
        3. Initializes the FastMCP server instance
        4. Discovers and initializes available search providers
        5. Sets up query analysis and routing components
        6. Configures caching (memory or Redis-backed)
        7. Registers MCP tools and HTTP routes

        The initialization is designed to be fail-safe - if certain providers
        or services (like Redis) are unavailable, the server will continue
        with reduced functionality rather than failing to start.

        Raises:
            ConfigurationError: If critical configuration is missing or invalid
            InitializationError: If core components fail to initialize
        """
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

        # Initialize providers dynamically from configuration
        self.providers = self._initialize_providers()
        logger.info(f"Initialized providers: {list(self.providers.keys())}")

        # Initialize components
        self.analyzer = QueryAnalyzer()

        # Initialize UNIFIED router with timeout configuration
        timeout_config = TimeoutConfig()
        self.router = UnifiedRouter(
            providers=self.providers,
            timeout_config=timeout_config,
        )

        self.merger = ResultMerger()

        # Initialize cache (either legacy or tiered)
        if self.settings.cache.redis_enabled:
            # Use tiered cache with Redis
            self.cache = TieredCache(
                redis_url=self.settings.cache.redis_url,
                redis_enabled=True,
                memory_ttl=self.settings.cache.memory_ttl,
                redis_ttl=self.settings.cache.redis_ttl,
                prefix=self.settings.cache.prefix,
                fingerprint_enabled=self.settings.cache.fingerprint_enabled,
            )

            if self.cache.redis_enabled:
                logger.info(
                    f"Initialized tiered cache with Redis at {self.settings.cache.redis_url}"
                )
            else:
                logger.warning(
                    "Redis not available, falling back to memory-only cache. "
                    "Install the 'redis' package to enable Redis caching."
                )
        else:
            # Use legacy memory-only cache
            self.cache = QueryCache(ttl=self.settings.cache_ttl)
            logger.info("Initialized memory-only cache")

        self.metrics = MetricsTracker()

        # Register tools and custom routes
        self._register_tools()
        self._register_custom_routes()

        # Provider tools will be registered when the server starts
        self._provider_tools_registered = False

    def _setup_middleware(self):
        """Set up and configure middleware components."""
        middleware_config = self.settings.middleware

        # Add error handler middleware (runs first - lowest order value)
        if middleware_config.error_handler.enabled:
            self.middleware_manager.add_middleware(
                ErrorHandlerMiddleware,
                enabled=middleware_config.error_handler.enabled,
                order=middleware_config.error_handler.order,
                include_traceback=middleware_config.error_handler.include_traceback,
                redact_sensitive_data=middleware_config.error_handler.redact_sensitive_data,
            )
            logger.info("Error handler middleware initialized")

        # Add logging middleware
        if middleware_config.logging.enabled:
            self.middleware_manager.add_middleware(
                LoggingMiddleware,
                enabled=middleware_config.logging.enabled,
                order=middleware_config.logging.order,
                log_level=middleware_config.logging.log_level,
                include_headers=middleware_config.logging.include_headers,
                include_body=middleware_config.logging.include_body,
                sensitive_headers=middleware_config.logging.sensitive_headers,
                max_body_size=middleware_config.logging.max_body_size,
            )
            logger.info("Logging middleware initialized")

        # Add authentication middleware
        if middleware_config.auth.enabled:
            self.middleware_manager.add_middleware(
                AuthMiddleware,
                enabled=middleware_config.auth.enabled,
                order=middleware_config.auth.order,
                api_keys=middleware_config.auth.api_keys,
                skip_auth_paths=middleware_config.auth.skip_auth_paths,
            )
            logger.info("Authentication middleware initialized")

        # Add rate limiting middleware
        if middleware_config.rate_limit.enabled:
            self.middleware_manager.add_middleware(
                RateLimitMiddleware,
                enabled=middleware_config.rate_limit.enabled,
                order=middleware_config.rate_limit.order,
                limit=middleware_config.rate_limit.limit,
                window=middleware_config.rate_limit.window,
                global_limit=middleware_config.rate_limit.global_limit,
                global_window=middleware_config.rate_limit.global_window,
                skip_paths=middleware_config.rate_limit.skip_paths,
            )
            logger.info("Rate limit middleware initialized")

        # Add retry middleware
        if middleware_config.retry.enabled:
            self.middleware_manager.add_middleware(
                RetryMiddleware,
                enabled=middleware_config.retry.enabled,
                order=middleware_config.retry.order,
                max_retries=middleware_config.retry.max_retries,
                base_delay=middleware_config.retry.base_delay,
                max_delay=middleware_config.retry.max_delay,
                exponential_base=middleware_config.retry.exponential_base,
                jitter=middleware_config.retry.jitter,
                skip_paths=middleware_config.retry.skip_paths,
            )
            logger.info("Retry middleware initialized")

        # Apply HTTP middleware to the FastMCP app
        self.mcp.http_app.add_middleware(
            MiddlewareHTTPWrapper, middleware_manager=self.middleware_manager
        )

    def _initialize_providers(self) -> dict[str, SearchProvider]:
        """Initialize providers from configuration."""
        settings = get_settings()
        providers = {}

        for provider_name in PROVIDER_CONFIGS:
            # Get provider settings
            provider_settings = getattr(settings.providers, provider_name, None)
            if not provider_settings:
                logger.warning(f"No settings found for provider {provider_name}")
                continue

            # Skip disabled providers
            if not provider_settings.enabled:
                logger.info(f"Provider {provider_name} is disabled")
                continue

            # Get API key
            api_key = None
            if hasattr(provider_settings, "api_key") and provider_settings.api_key:
                api_key = provider_settings.api_key.get_secret_value()

            # Create provider instance
            try:
                # Import provider class dynamically
                module_name = f"mcp_search_hub.providers.{provider_name}_mcp"
                # Convert provider name to CamelCase for class names
                class_name = (
                    "".join(word.capitalize() for word in provider_name.split("_"))
                    + "MCPProvider"
                )
                module = __import__(module_name, fromlist=[class_name])
                provider_class = getattr(module, class_name, None)

                if not provider_class:
                    logger.warning(f"Provider class not found for {provider_name}")
                    continue

                providers[provider_name] = provider_class(api_key=api_key)
                logger.info(f"Successfully initialized provider: {provider_name}")

            except ImportError as e:
                logger.error(f"Failed to import provider {provider_name}: {e}")
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
            """Execute a search query across multiple providers with middleware processing."""
            # Prepare parameters for middleware
            params = {
                "query": query,
                "max_results": max_results,
                "raw_content": raw_content,
                "advanced": advanced,
                "tool_name": "search",  # Include tool name for middleware
            }

            # Create handler function
            async def handler(p):
                # Extract params after middleware processing
                request_id = str(uuid.uuid4())
                ctx.info(f"Processing search request {request_id}: {p['query']}")

                # Build search query object
                search_query = SearchQuery(
                    query=p["query"],
                    max_results=p["max_results"],
                    raw_content=p["raw_content"],
                    advanced=p["advanced"],
                )

                # Use search_with_routing which handles caching internally
                response = await self.search_with_routing(search_query, request_id, ctx)
                return SearchResponse(
                    results=response.results, metadata=response.metadata
                )

            # Process through middleware
            return await self.middleware_manager.process_tool_request(
                params, ctx, handler
            )

        # Dynamically register provider-specific tools (deferred to server start)

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
                    # Create a tool wrapper that routes to the provider
                    tool_name = f"{provider_name}_{tool.name}"
                    tool_description = f"{tool.description} (via {provider_name})"

                    # Register the tool with FastMCP
                    self._register_single_provider_tool(
                        provider_name,
                        provider,
                        tool.name,
                        tool_name,
                        tool_description,
                        tool.parameters,
                    )

                logger.info(
                    f"Registered {len(tools)} tools for provider {provider_name}"
                )

            except Exception as e:
                logger.error(f"Failed to register tools for {provider_name}: {e}")

    def _register_single_provider_tool(
        self,
        provider_name: str,
        provider: SearchProvider,
        original_tool_name: str,
        tool_name: str,
        description: str,
        parameters: dict[str, Any],
    ):
        """Register a single provider tool with FastMCP."""

        @self.mcp.tool(
            name=tool_name,
            description=description,
        )
        async def provider_tool_wrapper(ctx: Context, **kwargs):
            """Wrapper function for provider-specific tools with middleware processing."""
            # Add tool metadata to parameters for middleware
            params = {
                **kwargs,
                "tool_name": tool_name,
                "provider_name": provider_name,
                "original_tool_name": original_tool_name,
            }

            # Create handler function
            async def handler(p):
                request_id = str(uuid.uuid4())
                ctx.info(
                    f"Invoking {provider_name} tool {original_tool_name} with request {request_id}"
                )

                try:
                    # Remove middleware metadata before invoking the tool
                    tool_params = {
                        k: v
                        for k, v in p.items()
                        if k
                        not in [
                            "tool_name",
                            "provider_name",
                            "original_tool_name",
                            "_retry_attempt",
                            "_retryable_request",
                        ]
                    }

                    # Use the provider's invoke_tool method
                    return await provider.invoke_tool(original_tool_name, tool_params)

                except Exception as e:
                    # Convert to appropriate provider error if needed
                    from .utils.errors import (
                        ProviderError,
                        ProviderRateLimitError,
                        ProviderServiceError,
                        ProviderTimeoutError,
                    )

                    if not isinstance(e, ProviderError):
                        # Wrap in appropriate provider error
                        if "time" in str(e).lower() or "timeout" in str(e).lower():
                            error = ProviderTimeoutError(
                                provider=provider_name,
                                operation=original_tool_name,
                                original_error=e,
                            )
                        elif "rate" in str(e).lower() or "limit" in str(e).lower():
                            error = ProviderRateLimitError(
                                provider=provider_name, original_error=e
                            )
                        else:
                            error = ProviderServiceError(
                                provider=provider_name,
                                message=f"Error invoking {provider_name} tool {original_tool_name}",
                                original_error=e,
                            )

                        ctx.error(f"{error.__class__.__name__}: {str(error)}")
                        raise error
                    # Pass through provider errors
                    ctx.error(f"{e.__class__.__name__}: {str(e)}")
                    raise

            # Process through middleware
            return await self.middleware_manager.process_tool_request(
                params, ctx, handler
            )

    def _register_custom_routes(self):
        """Register custom FastMCP HTTP routes."""
        # Use http_app for custom routes
        app = self.mcp.http_app

        @app.post("/search/combined")
        async def search_combined(request: Request) -> JSONResponse:
            """Execute a combined search across multiple providers."""
            try:
                data = await request.json()
                search_query = SearchQuery(**data)
                request_id = str(uuid.uuid4())

                # Create a mock context for HTTP requests
                class MockContext:
                    def info(self, msg):
                        logger.info(msg)

                    def warning(self, msg):
                        logger.warning(msg)

                    def error(self, msg):
                        logger.error(msg)

                mock_ctx = MockContext()

                # Use search_with_routing instead of manual process
                response = await self.search_with_routing(
                    search_query, request_id, mock_ctx
                )

                return JSONResponse(content=response.model_dump(mode="json"))

            except Exception as e:
                from .utils.errors import SearchError, http_error_response

                if isinstance(e, SearchError):
                    # Use the appropriate status code and error format
                    error_response = http_error_response(e)
                    return JSONResponse(
                        content=error_response,
                        status_code=e.status_code,
                    )
                # Generic error handling
                import traceback

                logger.error(f"Unhandled error in search_combined: {str(e)}")

                return JSONResponse(
                    content=http_error_response(
                        e,
                        status_code=500,
                        trace=traceback.format_exc() if self.settings.debug else None,
                    ),
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

        @app.get("/usage")
        async def usage_stats(request: Request) -> JSONResponse:
            """Provider usage statistics endpoint."""
            from .utils.usage_stats import UsageStats

            # Get provider status report
            status_report = UsageStats.get_provider_status_report()

            # Add additional provider info
            for name, provider in self.providers.items():
                if name in status_report:
                    # Add cost tracking info from provider
                    status_report[name]["cost_tracking"] = {
                        "base_cost": float(provider.base_cost)
                        if hasattr(provider, "base_cost")
                        else 0.01,
                        "estimated_daily_cost": float(
                            provider.budget_tracker.state.daily_cost
                        ),
                        "estimated_monthly_cost": float(
                            provider.budget_tracker.state.monthly_cost
                        ),
                    }

                    # Add capabilities
                    status_report[name]["capabilities"] = provider.get_capabilities()

            return JSONResponse(content=status_report)

    async def search_with_routing(
        self, search_query: SearchQuery, request_id: str, ctx: Context
    ) -> CombinedSearchResponse:
        """Execute a search using the unified router."""
        # Generate cache key
        cache_key = self.cache.generate_key(search_query)

        # Check cache based on the cache implementation type
        cached_result = None
        if isinstance(self.cache, TieredCache):
            # TieredCache has async methods
            cached_result = await self.cache.get_async(cache_key)
        else:
            # Legacy QueryCache is synchronous
            cached_result = self.cache.get(cache_key)

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
        ctx.info(f"Request {request_id} - Starting search with unified router")
        start_time = time.time()

        # Use the unified router which handles provider selection and execution
        results = await self.router.route_and_execute(
            query=search_query,
            features=features,
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
                "cache_key": cache_key,  # Include cache key for debugging
            },
        )

        # Cache the result based on the cache implementation type
        if isinstance(self.cache, TieredCache):
            # TieredCache has async methods
            await self.cache.set_async(cache_key, response)
        else:
            # Legacy QueryCache is synchronous
            self.cache.set(cache_key, response)

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

        # Close tiered cache if it's used
        if isinstance(self.cache, TieredCache):
            try:
                await self.cache.close()
                logger.info("Closed Redis connection in cache")
            except Exception as e:
                logger.error(f"Failed to close Redis connection in cache: {e}")

        logger.info("All resources closed")
