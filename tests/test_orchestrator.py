"""Concurrency, timeout, and fusion tests."""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal

import pytest

from mcp_search_hub.models import ProviderItem, ProviderResponse, SearchQuery
from mcp_search_hub.orchestrator import SearchOrchestrator, fuse_results
from mcp_search_hub.routing import RoutingPlanner
from tests.conftest import StubProviderSession, StubRegistry


def test_rrf_deduplicates_canonical_urls_and_preserves_provenance() -> None:
    responses = [
        ProviderResponse(
            provider="beta",
            latency_ms=1,
            results=[
                ProviderItem(
                    title="Same",
                    url="HTTPS://Example.com/docs/?utm_source=beta",
                    original_score=0.7,
                )
            ],
        ),
        ProviderResponse(
            provider="alpha",
            latency_ms=1,
            results=[
                ProviderItem(
                    title="Same page",
                    url="https://example.com/docs",
                    snippet="preferred deterministic content",
                    original_score=0.8,
                ),
                ProviderItem(
                    title="Duplicate from alpha",
                    url="https://example.com/docs/",
                    original_score=0.1,
                ),
                ProviderItem(title="Title only"),
            ],
        ),
    ]
    fused = fuse_results(responses, reciprocal_rank_k=60, limit=10)
    assert len(fused) == 2
    assert fused[0].snippet == "preferred deterministic content"
    assert [source.provider for source in fused[0].sources] == ["alpha", "beta"]
    assert fused[0].score == pytest.approx(2 / 61)


@pytest.mark.asyncio
async def test_execute_cancellation_drains_provider_tasks() -> None:
    class SlowCancellationSession(StubProviderSession):
        finished = False

        async def call_search(self, query: SearchQuery, operation_id: int) -> ProviderResponse:
            del query, operation_id
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                await asyncio.sleep(0.05)
                raise
            finally:
                self.finished = True
            return ProviderResponse(provider=self.identifier, latency_ms=0, results=[])

    session = SlowCancellationSession("slow")
    orchestrator = SearchOrchestrator(
        registry=StubRegistry([session]),
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )
    task = asyncio.create_task(orchestrator.execute(SearchQuery(query="general")))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert session.finished is True


@pytest.mark.asyncio
async def test_generation_cancellation_is_a_provider_timeout_not_caller_cancellation() -> None:
    class GenerationCancelledSession(StubProviderSession):
        async def call_search(
            self,
            query: SearchQuery,
            operation_id: int,
        ) -> ProviderResponse:
            del query, operation_id
            raise asyncio.CancelledError

    session = GenerationCancelledSession("reset")
    orchestrator = SearchOrchestrator(
        registry=StubRegistry([session]),
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )

    response = await orchestrator.execute(SearchQuery(query="generation reset"))

    assert response.timed_out_providers == ["reset"]
    assert session.timeout_count == 1


@pytest.mark.asyncio
async def test_request_deadline_includes_registry_startup() -> None:
    class SlowRegistry(StubRegistry):
        close_calls = 0

        async def startup(self) -> None:
            await asyncio.sleep(0.2)

        async def close(self) -> None:
            self.close_calls += 1
            await super().close()

    registry = SlowRegistry([StubProviderSession("alpha")])
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )
    started = time.perf_counter()
    response = await orchestrator.execute(SearchQuery(query="general", timeout_seconds=0.01))
    await asyncio.sleep(0)
    assert time.perf_counter() - started < 0.05
    assert response.timed_out_providers == ["alpha"]
    assert registry.close_calls == 0


@pytest.mark.asyncio
async def test_invalid_explicit_routes_fail_before_provider_recovery() -> None:
    class StalledRegistry(StubRegistry):
        recovery_calls = 0

        async def ensure_started(self, required_identifiers: set[str] | None = None) -> None:
            del required_identifiers
            self.recovery_calls += 1
            await asyncio.sleep(0.2)

    registry = StalledRegistry([StubProviderSession("alpha"), StubProviderSession("beta")])
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )

    with pytest.raises(ValueError, match="Unknown requested providers"):
        await orchestrator.execute(
            SearchQuery(
                query="general",
                providers=["alpha", "missing"],
                timeout_seconds=0.01,
            )
        )
    with pytest.raises(ValueError, match="server limit"):
        await orchestrator.execute(
            SearchQuery(
                query="general",
                providers=["alpha", "beta"],
                timeout_seconds=0.01,
            )
        )
    assert registry.recovery_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("use_request_budget", [False, True])
async def test_impossible_budget_fails_before_provider_recovery(
    use_request_budget: bool,
) -> None:
    class StalledRegistry(StubRegistry):
        recovery_calls = 0

        async def ensure_started(self, required_identifiers: set[str] | None = None) -> None:
            del required_identifiers
            self.recovery_calls += 1
            await asyncio.sleep(0.2)

    registry = StalledRegistry([StubProviderSession("alpha", cost="0.02")])
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(
            max_providers=1,
            default_budget_usd=None if use_request_budget else Decimal("0.01"),
        ),
        max_results=10,
        reciprocal_rank_k=60,
    )
    query = SearchQuery(
        query="general",
        providers=["alpha"],
        timeout_seconds=0.01,
        budget_usd=Decimal("0.01") if use_request_budget else None,
    )

    with pytest.raises(ValueError, match="budget is"):
        await orchestrator.execute(query)
    assert registry.recovery_calls == 0


@pytest.mark.asyncio
async def test_automatic_impossible_budget_fails_before_provider_recovery() -> None:
    class StalledRegistry(StubRegistry):
        recovery_calls = 0

        async def ensure_started(self, required_identifiers: set[str] | None = None) -> None:
            del required_identifiers
            self.recovery_calls += 1
            await asyncio.sleep(0.2)

    registry = StalledRegistry([StubProviderSession("alpha", cost="0.02")])
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )

    with pytest.raises(ValueError, match="fits the request budget"):
        await orchestrator.execute(
            SearchQuery(
                query="general",
                timeout_seconds=0.01,
                budget_usd=Decimal("0.01"),
            )
        )
    assert registry.recovery_calls == 0


@pytest.mark.asyncio
async def test_automatic_budget_waits_for_an_affordable_provider() -> None:
    class StalledAffordableRegistry(StubRegistry):
        required_identifiers: set[str] | None = None

        async def ensure_started(self, required_identifiers: set[str] | None = None) -> None:
            self.required_identifiers = required_identifiers
            await asyncio.sleep(0.2)

    cheap = StubProviderSession("cheap", cost="0.01")
    expensive = StubProviderSession("expensive", cost="0.02")
    expensive.ready = True
    registry = StalledAffordableRegistry([cheap, expensive])
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )

    response = await orchestrator.execute(
        SearchQuery(
            query="general",
            timeout_seconds=0.01,
            budget_usd=Decimal("0.015"),
        )
    )
    assert registry.required_identifiers == {"cheap"}
    assert response.timed_out_providers == ["cheap"]
    assert response.failed_providers == []
    assert expensive.invocations == 0


@pytest.mark.asyncio
async def test_global_timeout_records_only_provider_execution_time() -> None:
    class DelayedRegistry(StubRegistry):
        async def startup(self) -> None:
            await asyncio.sleep(0.05)
            await super().startup()

    session = StubProviderSession("slow", delay=0.5, timeout_seconds=1)
    orchestrator = SearchOrchestrator(
        registry=DelayedRegistry([session]),
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )
    response = await orchestrator.execute(SearchQuery(query="general", timeout_seconds=0.2))
    assert response.timed_out_providers == ["slow"]
    assert session.last_timeout_seconds is not None
    assert 0.05 < session.last_timeout_seconds < 0.19


@pytest.mark.asyncio
async def test_orchestrator_runs_providers_concurrently() -> None:
    sessions = [
        StubProviderSession("alpha", results=[ProviderItem(title="Alpha")], delay=0.05),
        StubProviderSession("beta", results=[ProviderItem(title="Beta")], delay=0.05),
    ]
    orchestrator = SearchOrchestrator(
        registry=StubRegistry(sessions),
        planner=RoutingPlanner(max_providers=2),
        max_results=10,
        reciprocal_rank_k=60,
    )
    started = time.perf_counter()
    response = await orchestrator.execute(SearchQuery(query="general"))
    assert time.perf_counter() - started < 0.09
    assert response.selected_providers == ["alpha", "beta"]
    assert len(response.results) == 2


@pytest.mark.asyncio
async def test_server_result_cap_is_forwarded_before_provider_io() -> None:
    session = StubProviderSession(
        "alpha",
        results=[ProviderItem(title=f"Result {index}") for index in range(5)],
    )
    orchestrator = SearchOrchestrator(
        registry=StubRegistry([session]),
        planner=RoutingPlanner(max_providers=1),
        max_results=2,
        reciprocal_rank_k=60,
    )
    response = await orchestrator.execute(SearchQuery(query="general", max_results=100))
    assert session.last_max_results == 2
    assert len(response.results) == 2


@pytest.mark.asyncio
async def test_orchestrator_returns_partial_failures_and_timeouts() -> None:
    sessions = [
        StubProviderSession("alpha", results=[ProviderItem(title="Alpha")], delay=0.01),
        StubProviderSession("broken", error=RuntimeError("private detail")),
        StubProviderSession("slow", delay=0.2, timeout_seconds=0.02),
    ]
    orchestrator = SearchOrchestrator(
        registry=StubRegistry(sessions),
        planner=RoutingPlanner(max_providers=3),
        max_results=10,
        reciprocal_rank_k=60,
    )
    response = await orchestrator.execute(SearchQuery(query="general", timeout_seconds=0.05))
    assert [result.title for result in response.results] == ["Alpha"]
    assert response.timed_out_providers == ["slow"]
    assert sessions[2].timeout_count == 1
    assert sessions[2].last_timeout_seconds == pytest.approx(0.02, abs=0.01)
    assert sessions[2].health().status.value == "unhealthy"
    assert response.failed_providers[0].provider == "broken"
    assert response.failed_providers[0].error_type == "RuntimeError"
    assert "private detail" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_global_timeout_marks_all_pending_providers() -> None:
    session = StubProviderSession(
        "slow",
        delay=0.2,
        timeout_seconds=1,
        results=[ProviderItem(title="Recovered")],
    )
    orchestrator = SearchOrchestrator(
        registry=StubRegistry([session]),
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )
    response = await orchestrator.execute(SearchQuery(query="general", timeout_seconds=0.01))
    assert response.results == []
    assert response.timed_out_providers == ["slow"]
    assert session.timeout_count == 1
    assert session.last_timeout_seconds == pytest.approx(0.01, abs=0.01)
    assert session.ready is True
    session.delay = 0
    recovered = await orchestrator.execute(SearchQuery(query="general"))
    assert [result.title for result in recovered.results] == ["Recovered"]
