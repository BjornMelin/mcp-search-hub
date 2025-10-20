"""End-to-end tests for the search orchestrator."""

from __future__ import annotations

import pytest

from mcp_search_hub.cache import SearchCache
from mcp_search_hub.metrics import MetricsTracker
from mcp_search_hub.models import SearchQuery
from mcp_search_hub.orchestrator import SearchOrchestrator
from mcp_search_hub.routing import QueryClassifier, RoutingPlanner

from tests.conftest import StubCall, StubProviderSession, StubRegistry


@pytest.mark.asyncio
async def test_orchestrator_executes_and_caches():
    sessions = [
        StubProviderSession(
            "alpha",
            tags={"general"},
            responses=[
                StubCall(
                    provider="alpha",
                    results=[{"title": "Doc", "url": "https://alpha", "score": 0.4}],
                    latency_ms=15.0,
                )
            ],
        )
    ]
    registry = StubRegistry(sessions)
    cache = SearchCache(
        memory_ttl=30,
        redis_enabled=False,
        redis_url=None,
        redis_ttl=60,
        prefix="search",
        ttl_jitter=0,
    )
    metrics = MetricsTracker()
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(QueryClassifier(), max_providers=1),
        cache=cache,
        metrics=metrics,
        max_results=5,
    )

    query = SearchQuery(query="general question", max_results=3)
    response = await orchestrator.execute(query)
    assert response.results[0].provider == "alpha"
    assert response.results[0].title == "Doc"
    assert sessions[0].invocations == 1

    # Second call should hit cache and avoid provider invocation
    cached = await orchestrator.execute(query)
    assert cached.results[0].title == "Doc"
    assert sessions[0].invocations == 1

    snapshot = metrics.snapshot()
    assert snapshot.total_queries == 2
    assert snapshot.total_successes == 2
    assert snapshot.cache_hits >= 1
