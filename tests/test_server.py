"""FastMCP protocol and server lifecycle tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, cast

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from pydantic import SecretStr

from mcp_search_hub.config import AppSettings
from mcp_search_hub.models import HealthStatus
from mcp_search_hub.providers import ProviderDefinition, ProviderRegistry
from mcp_search_hub.server import SearchServer
from tests.conftest import StubProviderSession, StubRegistry


def _payload(result: Any) -> dict[str, Any]:
    payload = result.structured_content
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


@pytest.mark.asyncio
async def test_in_memory_protocol_round_trip(
    stub_registry: StubRegistry,
) -> None:
    server = SearchServer(
        AppSettings(environment="test"),
        registry=stub_registry,
    )
    assert stub_registry.started is False
    async with Client(server.mcp) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools} == {"get_provider_info", "search"}
        tool_schemas = {
            tool.name: tool.model_dump(by_alias=True, exclude_none=True) for tool in tools
        }
        search_schema = tool_schemas["search"]
        search_properties = search_schema["inputSchema"]["properties"]
        assert search_properties["query"]["minLength"] == 1
        assert search_properties["query"]["maxLength"] == 4000
        assert search_properties["query"]["pattern"] == r"\S"
        assert search_properties["max_results"]["minimum"] == 1
        assert search_properties["max_results"]["maximum"] == 100
        provider_list_schema = search_properties["providers"]["anyOf"][0]
        assert provider_list_schema["minItems"] == 1
        assert provider_list_schema["items"]["pattern"] == r"\S"
        budget_string_schema = next(
            schema
            for schema in search_properties["budget_usd"]["anyOf"]
            if schema["type"] == "string"
        )
        assert "pattern" in budget_string_schema
        assert "results" in search_schema["outputSchema"]["properties"]
        assert "providers" in tool_schemas["get_provider_info"]["outputSchema"]["properties"]

        first = await client.call_tool("search", {"query": "technical docs"})
        second = await client.call_tool("search", {"query": "technical docs"})
        assert _payload(first)["results"][0]["title"] == "Alpha documentation"
        assert _payload(second)["results"] == _payload(first)["results"]
        assert stub_registry.sessions[0].invocations == 2

        info = await client.call_tool("get_provider_info", {})
        assert _payload(info)["providers"][0]["identifier"] == "alpha"
        assert stub_registry.started is True
    assert stub_registry.started is False


@pytest.mark.asyncio
async def test_health_route_and_catalog(stub_registry: StubRegistry) -> None:
    server = SearchServer(
        AppSettings(environment="test"),
        registry=stub_registry,
    )
    assert server.health().status == HealthStatus.UNHEALTHY
    catalog = server.provider_catalog()
    assert [entry.model_dump(mode="json") for entry in catalog] == [
        {
            "identifier": "alpha",
            "tool": "search",
            "tags": ["general", "technical"],
            "weight": 1.0,
            "timeout_seconds": 5.0,
            "estimated_cost_usd": "0.01",
        }
    ]
    app = server.http_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/health")
        assert response.status_code == 200
        payload = cast(dict[str, Any], response.json())
        assert payload["status"] == "healthy"
    assert stub_registry.started is False


@pytest.mark.asyncio
async def test_protocol_preserves_exact_cost_precision() -> None:
    exact_cost = "0.12345678901234567890123456789"
    registry = StubRegistry([StubProviderSession("precise", cost=exact_cost)])
    server = SearchServer(AppSettings(environment="test"), registry=registry)
    assert server.provider_catalog()[0].model_dump(mode="python")["estimated_cost_usd"] == Decimal(
        exact_cost
    )

    async with Client(server.mcp) as client:
        info = await client.call_tool("get_provider_info", {})
        assert _payload(info)["providers"][0]["estimated_cost_usd"] == exact_cost
        response = await client.call_tool(
            "search",
            {"query": "precision", "budget_usd": exact_cost},
        )
        assert _payload(response)["estimated_cost_usd"] == exact_cost
    assert Decimal(exact_cost) == registry.sessions[0].estimated_cost_usd


@pytest.mark.asyncio
async def test_cancelled_server_startup_closes_provider_recovery() -> None:
    startup_entered = asyncio.Event()

    @asynccontextmanager
    async def stalled_lifespan(_: FastMCP[Any]) -> AsyncGenerator[dict[str, object]]:
        startup_entered.set()
        await asyncio.Event().wait()
        yield {}  # pragma: no cover - required async-generator shape

    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="slow",
                transport=FastMCP("slow-provider", lifespan=stalled_lifespan),
                tool="search",
                timeout_seconds=1,
            )
        ]
    )
    server = SearchServer(AppSettings(environment="test"), registry=registry)
    app = server.http_app()

    async def run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            pass

    lifespan_task = asyncio.create_task(run_lifespan(), name="test-server-lifespan")
    await asyncio.wait_for(startup_entered.wait(), timeout=1)
    lifespan_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await lifespan_task
    assert registry.active_sessions() == []
    assert registry.recovering_identifiers() == set()
    assert not {
        task.get_name()
        for task in asyncio.all_tasks()
        if task.get_name() == "search-hub-recover-slow"
    }


@pytest.mark.asyncio
async def test_native_static_token_verifier_is_configured() -> None:
    server = SearchServer(AppSettings(environment="test", auth_tokens=[SecretStr("valid-token")]))
    verifier = server.mcp.auth
    assert isinstance(verifier, StaticTokenVerifier)
    assert await verifier.verify_token("invalid") is None
    token = await verifier.verify_token("valid-token")
    assert token is not None
    assert token.client_id == "configured-client-1"


def test_empty_provider_set_reports_degraded() -> None:
    server = SearchServer(AppSettings(environment="test"))
    health = server.health()
    assert health.status == HealthStatus.DEGRADED
    assert health.total_providers == 0


@pytest.mark.asyncio
async def test_run_http_rejects_unauthenticated_nonlocal_bind() -> None:
    server = SearchServer(AppSettings(environment="test", transport="stdio", host="0.0.0.0"))
    assert server.mcp.auth is None
    with pytest.raises(ValueError, match="network binds require"):
        await server.run_http()
