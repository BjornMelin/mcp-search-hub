"""Integration tests for the SearchServer wiring."""

from __future__ import annotations

import pytest

from mcp_search_hub.config import AppSettings
from mcp_search_hub.models import CombinedSearchResponse, SearchResult
from mcp_search_hub.providers.sessions import ProviderDefinition
from mcp_search_hub.server import SearchServer

from tests.conftest import StubRegistry


class StubOrchestrator:
    def __init__(self):
        self.calls = 0
        self.response = CombinedSearchResponse(
            results=[
                SearchResult(
                    title="Cached", url="https://cached", score=0.8, provider="alpha"
                )
            ],
            providers=[],
            metadata={},
        )

    async def execute(self, query):
        self.calls += 1
        return self.response


@pytest.mark.asyncio
async def test_server_health_and_metrics(stub_registry: StubRegistry):
    settings = AppSettings()
    server = SearchServer(settings=settings)
    server.registry = stub_registry
    server.registry._definitions = [
        ProviderDefinition(
            identifier="alpha",
            transport="stdio",  # placeholder; not used in test
            tool="search",
            tags={"general"},
            metadata={"quality": "high"},
        )
    ]
    server.orchestrator = StubOrchestrator()

    health = server.health()
    assert health.total_providers == len(stub_registry.active_sessions())

    metrics_response = await server._metrics_route(None)
    assert metrics_response.status_code == 200

    await server.metrics.record_success(["alpha"], latency_ms=12.0, cache_hit=False)
    metrics_response = await server._metrics_route(None)
    assert b"total_queries" in metrics_response.body

    tools = await server.mcp.get_tools()
    tool_names = {getattr(tool, "name", tool) for tool in tools}
    assert {"search", "get_provider_info"}.issubset(tool_names)
    catalog = server.provider_catalog()
    assert catalog[0]["identifier"] == "alpha"
