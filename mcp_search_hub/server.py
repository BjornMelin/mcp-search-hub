"""FastMCP-based server wiring for the search hub."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastmcp.server import FastMCP
from fastmcp.server.auth.auth import AccessToken, TokenVerifier
from fastmcp.server.middleware.error_handling import RetryMiddleware
from fastmcp.server.middleware.logging import (
    LoggingMiddleware,
    StructuredLoggingMiddleware,
)
from fastmcp.server.middleware.rate_limiting import SlidingWindowRateLimitingMiddleware
from starlette.responses import JSONResponse

from .cache import SearchCache
from .config import AppSettings, get_settings
from .metrics import MetricsTracker
from .models import HealthResponse, HealthStatus, SearchQuery
from .orchestrator import SearchOrchestrator
from .providers import ProviderRegistry
from .routing import QueryClassifier, RoutingPlanner

logger = logging.getLogger(__name__)


class StaticTokenVerifier(TokenVerifier):
    """Simple token verifier backed by an in-memory token set."""

    def __init__(self, tokens: set[str]):
        super().__init__()
        self._tokens = tokens

    async def verify_token(self, token: str) -> AccessToken | None:
        if token in self._tokens:
            return AccessToken(
                token=token, client_id="search-hub", scopes=[], expires_at=None
            )
        return None


class SearchServer:
    """Public entry point that configures FastMCP with modern primitives."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry = ProviderRegistry.from_settings(self.settings)
        classifier = QueryClassifier()
        planner = RoutingPlanner(
            classifier, max_providers=self.settings.router.max_providers
        )
        self.metrics = MetricsTracker()
        self.cache = SearchCache(
            memory_ttl=self.settings.cache.memory_ttl,
            redis_enabled=self.settings.cache.redis_enabled,
            redis_url=self.settings.cache.redis_url,
            redis_ttl=self.settings.cache.redis_ttl,
            prefix=self.settings.cache.prefix,
            ttl_jitter=self.settings.cache.ttl_jitter,
        )
        self.orchestrator = SearchOrchestrator(
            registry=self.registry,
            planner=planner,
            cache=self.cache,
            metrics=self.metrics,
            max_results=self.settings.results.max_results,
        )

        self.mcp = FastMCP(
            name=self.settings.app_name,
            instructions=(
                "Unified search hub exposing multiple MCP providers. "
                "Queries are routed automatically; prefer providing topical hints when available."
            ),
            log_level=self.settings.log_level,
        )
        self._configure_middleware()
        self._register_tools()
        middleware_stack = self._build_http_middleware()
        self._http_app = self.mcp.http_app(
            path=self.settings.streamable_http_path,
            middleware=middleware_stack,
        )
        self._http_app.add_route("/health", self._health_route)
        self._http_app.add_route("/metrics", self._metrics_route)

    async def startup(self) -> None:
        """Initialize provider sessions."""

        await self.registry.startup()

    async def shutdown(self) -> None:
        """Shutdown provider sessions."""

        await self.registry.close()

    def http_app(self):
        """Return the Starlette application for HTTP transport."""

        return self._http_app

    async def run_http(self) -> None:
        """Run the server using FastMCP's HTTP transport."""

        await self.startup()
        try:
            await self.mcp.run_streamable_http_async(
                host=self.settings.host,
                port=self.settings.port,
                path=self.settings.streamable_http_path,
            )
        finally:
            await self.shutdown()

    async def run_stdio(self) -> None:
        """Run the server using stdio transport."""

        await self.startup()
        try:
            await self.mcp.run_stdio_async()
        finally:
            await self.shutdown()

    def health(self) -> HealthResponse:
        """Return hub health information."""

        provider_states = self.registry.health()
        healthy_count = sum(
            1
            for state in provider_states.values()
            if state.status == HealthStatus.HEALTHY
        )
        if not provider_states:
            overall = HealthStatus.DEGRADED
        elif healthy_count == len(provider_states):
            overall = HealthStatus.HEALTHY
        elif healthy_count == 0:
            overall = HealthStatus.UNHEALTHY
        else:
            overall = HealthStatus.DEGRADED
        return HealthResponse(
            status=overall,
            healthy_providers=healthy_count,
            total_providers=len(provider_states),
            providers=provider_states,
            extra={"environment": self.settings.environment},
        )

    def provider_catalog(self) -> list[dict[str, Any]]:
        """Return metadata about configured providers."""

        catalog = []
        for definition in self.registry.definitions():
            catalog.append(
                {
                    "identifier": definition.identifier,
                    "tool": definition.tool,
                    "tags": sorted(definition.tags),
                    "metadata": definition.metadata,
                    "timeout": definition.timeout,
                }
            )
        return catalog

    def _configure_middleware(self) -> None:
        log_level = getattr(logging, self.settings.log_level, logging.INFO)
        if self.settings.middleware.structured_logging:
            self.mcp.add_middleware(
                StructuredLoggingMiddleware(
                    log_level=log_level,
                    include_payloads=self.settings.middleware.include_payloads,
                )
            )
        else:
            self.mcp.add_middleware(
                LoggingMiddleware(
                    log_level=log_level,
                    include_payloads=self.settings.middleware.include_payloads,
                )
            )

        if self.settings.middleware.rate_limit_enabled:
            window_minutes = max(
                1, self.settings.middleware.rate_limit_window_seconds // 60 or 1
            )
            limiter = SlidingWindowRateLimitingMiddleware(
                max_requests=self.settings.middleware.rate_limit_requests,
                window_minutes=window_minutes,
            )
            self.mcp.add_middleware(limiter)

        retry = RetryMiddleware(
            max_retries=self.settings.retry.max_retries,
            base_delay=self.settings.retry.base_delay,
            max_delay=self.settings.retry.max_delay,
            backoff_multiplier=self.settings.retry.backoff_multiplier,
        )
        self.mcp.add_middleware(retry)

    def _register_tools(self) -> None:
        @self.mcp.tool(
            name="search",
            description="Execute a federated search across configured providers.",
        )
        async def search_tool(
            query: str,
            max_results: int = 10,
            include_raw_content: bool = False,
            tags: list[str] | None = None,
            advanced: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            request = SearchQuery(
                query=query,
                max_results=min(max_results, self.settings.results.max_results),
                include_raw_content=include_raw_content,
                tags=set(tags or []),
                advanced=advanced or {},
            )
            response = await self.orchestrator.execute(request)
            return response.model_dump(mode="json")

        @self.mcp.tool(
            name="get_provider_info",
            description="Return provider metadata exposed by the hub.",
        )
        async def provider_info() -> dict[str, Any]:
            return {"providers": self.provider_catalog()}

    def _build_http_middleware(self):
        if not (
            self.settings.middleware.auth_enabled
            and self.settings.middleware.auth_api_keys
        ):
            return None
        verifier = StaticTokenVerifier(set(self.settings.middleware.auth_api_keys))
        return verifier.get_middleware()

    async def _health_route(self, request):  # pragma: no cover - exercised via tests
        response = self.health()
        return JSONResponse(response.model_dump(mode="json"))

    async def _metrics_route(self, request):  # pragma: no cover - exercised via tests
        snapshot = self.metrics.snapshot()
        return JSONResponse(asdict(snapshot))


__all__ = ["SearchServer"]
