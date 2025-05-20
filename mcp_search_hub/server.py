"""FastMCP search server implementation using unified router."""

import asyncio
import json
import time
import uuid
from typing import Any

from fastmcp import Context, FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import get_settings
from .middleware import (
    AuthMiddleware,
    LoggingMiddleware,
    MiddlewareManager,
    RateLimitMiddleware,
)
from .models.base import (
    ErrorResponse,
    HealthResponse,
    HealthStatus,
    MetricsResponse,
    ProviderStatus,
)
from .models.query import SearchQuery
from .models.results import CombinedSearchResponse, SearchResponse
from .models.router import TimeoutConfig
from .openapi import custom_openapi
from .providers.base import SearchProvider
from .providers.provider_config import PROVIDER_CONFIGS
from .query_routing.analyzer import QueryAnalyzer
from .query_routing.unified_router import UnifiedRouter
from .result_processing.merger import ResultMerger
from .utils.cache import QueryCache
from .utils.logging import get_logger
from .utils.metrics import MetricsTracker

logger = get_logger(__name__)


class SearchServer:
    """FastMCP search server implementation with unified routing."""

    def __init__(self):
        # Initialize settings
        self.settings = get_settings()

        # Initialize middleware manager
        self.middleware_manager = MiddlewareManager()
        self._setup_middleware()

        # Initialize FastMCP server with OpenAPI documentation
        self.mcp = FastMCP(
            name="MCP Search Hub",
            instructions="""
            This server provides access to multiple search providers through a unified interface.
            Use the search tool to find information with automatic provider selection.
            """,
            log_level=self.settings.log_level,
            title="MCP Search Hub API",
            description="Intelligent multi-provider search aggregation server built on FastMCP 2.0",
            version="1.0.0",
            docs_url="/docs",  # URL for Swagger UI
            redoc_url="/redoc",  # URL for ReDoc UI
            openapi_url="/openapi.json",  # URL for OpenAPI JSON schema
        )

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
        self.cache = QueryCache(ttl=self.settings.cache_ttl)
        self.metrics = MetricsTracker()

        # Register tools and custom routes
        self._register_tools()
        self._register_custom_routes()
        
        # Set custom OpenAPI schema generator
        self.mcp.http_app.openapi = lambda: custom_openapi(self.mcp.http_app)

        # Provider tools will be registered when the server starts
        self._provider_tools_registered = False

    def _setup_middleware(self):
        """Set up and configure middleware components."""
        middleware_config = self.settings.middleware

        # Add logging middleware
        if middleware_config.logging.enabled:
            logging_config = middleware_config.logging
            self.middleware_manager.add_middleware(
                LoggingMiddleware,
                order=logging_config.order,
                log_level=logging_config.log_level,
                include_headers=logging_config.include_headers,
                include_body=logging_config.include_body,
                sensitive_headers=logging_config.sensitive_headers,
                max_body_size=logging_config.max_body_size,
            )
            logger.info("Logging middleware enabled")

        # Add authentication middleware
        if middleware_config.auth.enabled:
            auth_config = middleware_config.auth
            self.middleware_manager.add_middleware(
                AuthMiddleware,
                order=auth_config.order,
                api_keys=auth_config.api_keys,
                skip_auth_paths=auth_config.skip_auth_paths,
            )
            logger.info(
                f"Authentication middleware enabled with {len(auth_config.api_keys)} API keys"
            )

        # Add rate limiting middleware
        if middleware_config.rate_limit.enabled:
            rate_limit_config = middleware_config.rate_limit
            self.middleware_manager.add_middleware(
                RateLimitMiddleware,
                order=rate_limit_config.order,
                limit=rate_limit_config.limit,
                window=rate_limit_config.window,
                global_limit=rate_limit_config.global_limit,
                global_window=rate_limit_config.global_window,
                skip_paths=rate_limit_config.skip_paths,
            )
            logger.info(
                f"Rate limiting middleware enabled: {rate_limit_config.limit} "
                f"requests per {rate_limit_config.window}s"
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

        # Define the original search function
        async def _search_implementation(
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

        # Create a middleware-wrapped search function
        async def search_with_middleware(
            query: str,
            ctx: Context,
            max_results: int = 10,
            raw_content: bool = False,
            advanced: dict[str, Any] | None = None,
        ) -> SearchResponse:
            """Execute a search query with middleware processing."""
            # Prepare parameters for middleware
            params = {
                "query": query,
                "max_results": max_results,
                "raw_content": raw_content,
                "advanced": advanced,
                "tool_name": "search",  # Include tool name for middleware
            }

            # Create a handler that will call the implementation with unpacked params
            async def handler(**p):
                # Remove tool_name from params before passing to implementation
                if "tool_name" in p:
                    p = {k: v for k, v in p.items() if k != "tool_name"}
                return await _search_implementation(**p)

            # Process through middleware
            return await self.middleware_manager.process_tool_request(
                params, ctx, handler
            )

        # Register the middleware-wrapped function with enhanced documentation
        self.mcp.tool(
            name="search",
            description="Search across multiple providers with intelligent routing",
            parameters={
                "query": {
                    "type": "string",
                    "description": "The search query text"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 10
                },
                "raw_content": {
                    "type": "boolean",
                    "description": "Whether to include raw content in results",
                    "default": False
                },
                "advanced": {
                    "type": "object",
                    "description": "Advanced search parameters (optional)",
                    "default": None
                }
            },
            returns={
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                                "snippet": {"type": "string"},
                                "source": {"type": "string"},
                                "score": {"type": "number"}
                            }
                        }
                    },
                    "query": {"type": "string"},
                    "providers_used": {"type": "array", "items": {"type": "string"}},
                    "total_results": {"type": "integer"},
                    "total_cost": {"type": "number"},
                    "timing_ms": {"type": "number"}
                }
            },
            examples=[
                {
                    "query": "latest advancements in artificial intelligence",
                    "max_results": 5,
                    "raw_content": False,
                    "advanced": None
                },
                {
                    "query": "climate change studies 2025",
                    "max_results": 10,
                    "raw_content": True,
                    "advanced": {"content_type": "SCIENTIFIC"}
                }
            ]
        )(search_with_middleware)

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

        # Define the original implementation
        async def _provider_implementation(ctx: Context, **kwargs):
            """Original provider tool implementation."""
            request_id = str(uuid.uuid4())
            ctx.info(
                f"Invoking {provider_name} tool {original_tool_name} with request {request_id}"
            )

            try:
                # Use the provider's invoke_tool method
                return await provider.invoke_tool(original_tool_name, kwargs)
            except Exception as e:
                ctx.error(
                    f"Error invoking {provider_name} tool {original_tool_name}: {e}"
                )
                raise

        # Create a middleware-wrapped function
        async def provider_tool_with_middleware(ctx: Context, **kwargs):
            """Middleware-processed provider tool wrapper."""
            # Add tool info to parameters
            params = {
                **kwargs,
                "tool_name": tool_name,
                "provider": provider_name,
                "original_tool_name": original_tool_name,
            }

            # Create handler that will invoke the implementation
            async def handler(**p):
                # Clean tool-specific keys before passing to implementation
                clean_params = {
                    k: v
                    for k, v in p.items()
                    if k not in ["tool_name", "provider", "original_tool_name"]
                }
                return await _provider_implementation(ctx, **clean_params)

            # Process through middleware
            return await self.middleware_manager.process_tool_request(
                params, ctx, handler
            )

        # Add provider-specific examples
        examples = []
        if provider_name == "firecrawl" and original_tool_name in ["firecrawl_search", "firecrawl_scrape"]:
            examples.append({
                "summary": "Basic search example",
                "value": {"query": "latest AI research papers"}
            })
        elif provider_name == "tavily":
            examples.append({
                "summary": "Search with advanced options",
                "value": {"query": "climate change", "search_depth": "advanced"}
            })
        elif provider_name == "perplexity":
            examples.append({
                "summary": "Ask a research question",
                "value": {"messages": [{"role": "user", "content": "What are the latest developments in quantum computing?"}]}
            })
        elif provider_name == "exa":
            examples.append({
                "summary": "Academic search example",
                "value": {"query": "machine learning in healthcare"}
            })
        elif provider_name == "linkup":
            examples.append({
                "summary": "Deep web search",
                "value": {"query": "emerging technologies 2025", "depth": "deep"}
            })
            
        # Register the middleware-wrapped function with provider-specific documentation
        self.mcp.tool(
            name=tool_name,
            description=description,
            parameters=parameters,
            examples=examples if examples else None,
        )(provider_tool_with_middleware)

    def _register_custom_routes(self):
        """Register custom FastMCP HTTP routes."""
        # Use http_app for custom routes
        app = self.mcp.http_app

        @app.post(
            "/search/combined",
            summary="Execute a combined search across multiple providers",
            description="Performs a unified search across all enabled providers, with intelligent routing and result merging.",
            tags=["Search"],
            response_model=CombinedSearchResponse,
            responses={
                200: {
                    "description": "Successful search with combined results",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/CombinedSearchResponse"}
                        }
                    },
                },
                400: {
                    "description": "Bad request - invalid query parameters",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                        }
                    },
                },
                500: {
                    "description": "Server error during search",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                        }
                    },
                },
            },
        )
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
                import traceback

                return JSONResponse(
                    content={
                        "error": str(e),
                        "trace": traceback.format_exc(),
                    },
                    status_code=500,
                )

        @app.get(
            "/health",
            summary="Check server health status",
            description="Returns the health status of the server and all enabled providers.",
            tags=["Health"],
            response_model=HealthResponse,
            responses={
                200: {
                    "description": "Server is healthy",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/HealthResponse"}
                        }
                    }
                },
                503: {
                    "description": "Server is unhealthy or degraded",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/HealthResponse"}
                        }
                    }
                }
            }
        )
        async def health_check(request: Request) -> JSONResponse:
            """Health check endpoint."""
            # Build provider health status
            provider_health = {}
            for name, provider in self.providers.items():
                status = provider.check_status()
                if status:
                    provider_health[name] = ProviderStatus(
                        name=status.name,
                        health=status.health,
                        status=status.status,
                        message=status.message,
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

        @app.get(
            "/metrics",
            summary="Get server performance metrics",
            description="Returns detailed performance metrics for the server and all providers.",
            tags=["Metrics"],
            response_model=MetricsResponse,
            responses={
                200: {
                    "description": "Metrics retrieved successfully",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/MetricsResponse"}
                        }
                    }
                }
            }
        )
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
        
        @app.get(
            "/export-openapi",
            summary="Export OpenAPI schema as a downloadable file",
            description="Generates the OpenAPI schema for the API and returns it as a downloadable JSON file.",
            tags=["Documentation"],
            responses={
                200: {
                    "description": "OpenAPI schema JSON file",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "additionalProperties": True
                            }
                        }
                    }
                }
            }
        )
        async def export_openapi(request: Request) -> JSONResponse:
            """Export OpenAPI schema as a downloadable file."""
            schema = app.openapi()
            
            # Return schema as a downloadable file
            from starlette.responses import Response
            return Response(
                content=json.dumps(schema, indent=2),
                media_type="application/json",
                headers={"Content-Disposition": "attachment; filename=mcp-search-hub-openapi.json"}
            )

    async def search_with_routing(
        self, search_query: SearchQuery, request_id: str, ctx: Context
    ) -> CombinedSearchResponse:
        """Execute a search using the unified router."""
        # Check cache first
        cache_key = self.cache.generate_key(search_query)
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
            },
        )

        # Cache the result
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

        # Apply HTTP middlewares to app
        # Note: They are applied in reverse order (last added = outermost middleware)
        app = self.mcp.http_app

        # Create custom HTTP middleware using our middleware manager
        class MiddlewareHTTPWrapper(BaseHTTPMiddleware):
            """HTTP middleware wrapper for the middleware manager."""

            def __init__(self, app, middleware_manager):
                super().__init__(app)
                self.middleware_manager = middleware_manager

            async def dispatch(self, request, call_next):
                """Process HTTP request through middleware manager."""
                try:
                    return await self.middleware_manager.process_http_request(
                        request, call_next
                    )
                except Exception as e:
                    # If middleware raised an exception with a JSONResponse, return it
                    if (
                        isinstance(e.__cause__, JSONResponse)
                        or hasattr(e, "args")
                        and len(e.args) > 0
                        and isinstance(e.args[0], JSONResponse)
                    ):
                        if isinstance(e.__cause__, JSONResponse):
                            return e.__cause__
                        return e.args[0]

                    # Otherwise create a generic error response
                    logger.error(f"Error in middleware: {str(e)}")
                    error_response = ErrorResponse(
                        error="ServerError",
                        message="An error occurred processing the request",
                        status_code=500,
                    )
                    return JSONResponse(
                        status_code=500, content=error_response.model_dump()
                    )

        # Apply our middleware wrapper
        self.mcp.http_app = MiddlewareHTTPWrapper(app, self.middleware_manager)

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

        logger.info("All providers closed")
