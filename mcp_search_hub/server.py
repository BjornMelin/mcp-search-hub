"""FastMCP 3 server wiring."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware
from fastmcp.server.middleware.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.rate_limiting import SlidingWindowRateLimitingMiddleware
from pydantic import Field, WithJsonSchema
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import __version__
from .config import AppSettings, get_settings
from .models import (
    CombinedSearchResponse,
    HealthResponse,
    HealthStatus,
    ProviderCatalogEntry,
    ProviderCatalogResponse,
    SearchQuery,
)
from .orchestrator import SearchOrchestrator
from .providers import ProviderRegistry, ProviderRegistryProtocol
from .routing import RoutingPlanner

SearchText = Annotated[str, Field(min_length=1, max_length=4000, pattern=r"\S")]
ProviderIdentifier = Annotated[str, Field(min_length=1, pattern=r"\S")]
ProviderIdentifiers = Annotated[list[ProviderIdentifier], Field(min_length=1)]
BudgetUSD = Annotated[
    Decimal,
    Field(gt=Decimal("0")),
    WithJsonSchema(
        {
            "anyOf": [
                {"type": "number", "exclusiveMinimum": 0},
                {
                    "type": "string",
                    "pattern": (
                        r"^(?:\+?(?:[0-9]*[1-9][0-9]*)(?:\.[0-9]*)?"
                        r"|\+?0*\.[0-9]*[1-9][0-9]*)(?:[eE][+-]?[0-9]+)?$"
                    ),
                },
            ]
        }
    ),
]


class SearchServer:
    """Configure the public MCP surface from one typed settings object."""

    def __init__(
        self,
        settings: AppSettings | None = None,
        registry: ProviderRegistryProtocol | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or ProviderRegistry.from_settings(self.settings)
        self.orchestrator = SearchOrchestrator(
            registry=self.registry,
            planner=RoutingPlanner(
                max_providers=self.settings.router.max_providers,
                default_budget_usd=self.settings.router.default_budget_usd,
            ),
            max_results=self.settings.results.max_results,
            reciprocal_rank_k=self.settings.results.reciprocal_rank_k,
        )

        @asynccontextmanager
        async def lifespan(_: FastMCP[Any]):
            try:
                await self.registry.startup()
                yield {"registry": self.registry}
            finally:
                await self.registry.close()

        self.mcp = FastMCP(
            name=self.settings.app_name,
            version=__version__,
            instructions=(
                "Federated search with deterministic provider routing, reciprocal-rank "
                "fusion, explicit provenance, and bounded cost and time."
            ),
            auth=self._auth_verifier(),
            middleware=self._middleware(),
            lifespan=lifespan,
        )
        self._register_tools()
        self._register_routes()

    def health(self) -> HealthResponse:
        """Return current provider lifecycle health without making network calls."""

        states = self.registry.health()
        total = len(self.registry.definitions())
        healthy = sum(state.status == HealthStatus.HEALTHY for state in states.values())
        if total == 0:
            status = HealthStatus.DEGRADED
        elif healthy == total:
            status = HealthStatus.HEALTHY
        elif healthy == 0:
            status = HealthStatus.UNHEALTHY
        else:
            status = HealthStatus.DEGRADED
        return HealthResponse(
            status=status,
            healthy_providers=healthy,
            total_providers=total,
            providers=states,
            extra={"environment": self.settings.environment, "version": __version__},
        )

    def provider_catalog(self) -> list[ProviderCatalogEntry]:
        """Return non-secret provider capabilities and routing inputs."""

        return [
            ProviderCatalogEntry(
                identifier=definition.identifier,
                tool=definition.tool,
                tags=sorted(definition.tags),
                weight=definition.weight,
                timeout_seconds=definition.timeout_seconds,
                estimated_cost_usd=definition.estimated_cost_usd,
            )
            for definition in self.registry.definitions()
        ]

    def http_app(self):
        """Build the ASGI application for embedding or tests."""

        return self.mcp.http_app(path=self.settings.http_path)

    async def run_http(self) -> None:
        self.settings.validate_http_bind()
        await self.mcp.run_http_async(
            transport="http",
            host=self.settings.host,
            port=self.settings.port,
            path=self.settings.http_path,
            log_level=self.settings.log_level,
        )

    async def run_stdio(self) -> None:
        await self.mcp.run_stdio_async(log_level=self.settings.log_level)

    def _auth_verifier(self) -> StaticTokenVerifier | None:
        tokens: dict[str, dict[str, Any]] = {
            secret.get_secret_value(): {
                "client_id": f"configured-client-{index}",
                "scopes": list[str](),
            }
            for index, secret in enumerate(self.settings.auth_tokens, start=1)
        }
        return StaticTokenVerifier(tokens=tokens) if tokens else None

    def _middleware(self) -> list[Middleware]:
        middleware: list[Middleware] = [
            StructuredLoggingMiddleware(
                log_level=getattr(logging, self.settings.log_level),
                include_payloads=self.settings.middleware.include_log_payloads,
            ),
            SlidingWindowRateLimitingMiddleware(
                max_requests=self.settings.middleware.rate_limit_requests,
                window_minutes=self.settings.middleware.rate_limit_window_minutes,
                get_client_id=_rate_limit_client_id,
            ),
        ]
        return middleware

    def _register_tools(self) -> None:
        async def search_tool(
            query: SearchText,
            max_results: Annotated[int, Field(ge=1, le=100)] = 10,
            include_raw_content: bool = False,
            providers: ProviderIdentifiers | None = None,
            tags: list[str] | None = None,
            timeout_seconds: Annotated[float | None, Field(gt=0.0, le=300.0)] = None,
            budget_usd: BudgetUSD | None = None,
        ) -> CombinedSearchResponse:
            request = SearchQuery(
                query=query,
                max_results=max_results,
                include_raw_content=include_raw_content,
                providers=providers,
                tags=set(tags or []),
                timeout_seconds=(
                    timeout_seconds
                    if timeout_seconds is not None
                    else self.settings.router.default_timeout_seconds
                ),
                budget_usd=budget_usd,
            )
            return await self.orchestrator.execute(request)

        self.mcp.tool(
            name="search",
            description="Search selected providers and return fused results with provenance.",
        )(search_tool)

        async def get_provider_info() -> ProviderCatalogResponse:
            return ProviderCatalogResponse(providers=self.provider_catalog())

        self.mcp.tool(
            name="get_provider_info",
            description="List configured provider routing and cost metadata.",
        )(get_provider_info)

    def _register_routes(self) -> None:
        async def health_route(_: Request) -> Response:
            return JSONResponse(self.health().model_dump(mode="json"))

        self.mcp.custom_route("/health", methods=["GET"], include_in_schema=True)(health_route)


def _rate_limit_client_id(_context: MiddlewareContext[Any]) -> str:
    token = get_access_token()
    if token is not None:
        return f"client:{token.client_id}"
    return "anonymous"


__all__ = ["SearchServer"]
