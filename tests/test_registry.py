"""Real provider registry lifecycle tests."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastmcp import FastMCP

from mcp_search_hub.config import AppSettings, ProviderSettings
from mcp_search_hub.models import HealthStatus, SearchQuery
from mcp_search_hub.orchestrator import SearchOrchestrator
from mcp_search_hub.providers import MCPProviderSession, ProviderDefinition, ProviderRegistry
from mcp_search_hub.routing import RoutingPlanner


def _working_provider() -> FastMCP:
    server = FastMCP("working-provider")

    def search(query: str, max_results: int, include_raw_content: bool) -> dict[str, object]:
        return {
            "results": [
                {
                    "title": query,
                    "content": "body" if include_raw_content else None,
                }
            ][:max_results]
        }

    server.tool(search)
    return server


def _broken_provider() -> FastMCP:
    @asynccontextmanager
    async def broken_lifespan(_: FastMCP[Any]) -> AsyncGenerator[dict[str, object]]:
        raise ConnectionError("startup failed")
        yield {}  # pragma: no cover - required async-generator shape

    return FastMCP("broken-provider", lifespan=broken_lifespan)


def _stalled_provider() -> FastMCP:
    @asynccontextmanager
    async def stalled_lifespan(_: FastMCP[Any]) -> AsyncGenerator[dict[str, object]]:
        await asyncio.sleep(10)
        yield {}

    return FastMCP("stalled-provider", lifespan=stalled_lifespan)


def _slow_search_provider() -> FastMCP:
    server = FastMCP("slow-search-provider")

    async def search(query: str, max_results: int, include_raw_content: bool) -> dict[str, object]:
        await asyncio.sleep(0.05)
        return {
            "results": [{"title": query, "content": "body" if include_raw_content else None}][
                :max_results
            ]
        }

    server.tool(search)
    return server


def _cancellation_resistant_provider(state: dict[str, float]) -> FastMCP:
    server = FastMCP("cancellation-resistant-provider")

    async def search(query: str, max_results: int, include_raw_content: bool) -> dict[str, object]:
        if state["delay"]:
            try:
                await asyncio.sleep(state["delay"])
            except asyncio.CancelledError:
                await asyncio.sleep(0.02)
        return {
            "results": [{"title": query, "content": "body" if include_raw_content else None}][
                :max_results
            ]
        }

    server.tool(search)
    return server


def _fail_once_provider(state: dict[str, int]) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_: FastMCP[Any]) -> AsyncGenerator[dict[str, object]]:
        state["attempts"] += 1
        if state["attempts"] == 1:
            raise ConnectionError("transient startup failure")
        yield {}

    server = FastMCP("fail-once-provider", lifespan=lifespan)

    def search(query: str, max_results: int, include_raw_content: bool) -> dict[str, object]:
        return {
            "results": [{"title": query, "content": "body" if include_raw_content else None}][
                :max_results
            ]
        }

    server.tool(search)
    return server


def _counted_provider(state: dict[str, int]) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_: FastMCP[Any]) -> AsyncGenerator[dict[str, object]]:
        state["attempts"] += 1
        yield {}

    return FastMCP("counted-provider", lifespan=lifespan)


def _fail_then_stall_provider(state: dict[str, int]) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_: FastMCP[Any]) -> AsyncGenerator[dict[str, object]]:
        state["attempts"] += 1
        if state["attempts"] == 1:
            raise ConnectionError("transient startup failure")
        await asyncio.sleep(10)
        yield {}

    return FastMCP("fail-then-stall-provider", lifespan=lifespan)


def _fail_then_wait_provider(state: dict[str, int], release: asyncio.Event) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_: FastMCP[Any]) -> AsyncGenerator[dict[str, object]]:
        state["attempts"] += 1
        if state["attempts"] == 1:
            raise ConnectionError("transient startup failure")
        await release.wait()
        yield {}

    server = FastMCP("fail-then-wait-provider", lifespan=lifespan)

    def search(query: str, max_results: int, include_raw_content: bool) -> dict[str, object]:
        return {
            "results": [{"title": query, "content": "body" if include_raw_content else None}][
                :max_results
            ]
        }

    server.tool(search)
    return server


def _cancellation_suppressing_startup_provider(
    entered: asyncio.Event,
    release: asyncio.Event,
) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_: FastMCP[Any]) -> AsyncGenerator[dict[str, object]]:
        entered.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue
        yield {}

    return FastMCP("cancellation-suppressing-startup-provider", lifespan=lifespan)


def _cancellation_suppressing_teardown_provider(
    teardown_entered: asyncio.Event,
    release: asyncio.Event,
) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_: FastMCP[Any]) -> AsyncGenerator[dict[str, object]]:
        try:
            yield {}
        finally:
            teardown_entered.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    continue

    return FastMCP("cancellation-suppressing-teardown-provider", lifespan=lifespan)


def _blocking_provider(state: dict[str, int], finish: asyncio.Event) -> FastMCP:
    server = FastMCP("blocking-provider")

    async def search(query: str, max_results: int, include_raw_content: bool) -> dict[str, object]:
        state["active"] += 1
        state["started"] += 1
        state["max_active"] = max(state["max_active"], state["active"])
        try:
            try:
                await finish.wait()
            except asyncio.CancelledError:
                await finish.wait()
            return {
                "results": [{"title": query, "content": "body" if include_raw_content else None}][
                    :max_results
                ]
            }
        finally:
            state["active"] -= 1

    server.tool(search)
    return server


@pytest.mark.asyncio
async def test_registry_starts_concurrently_tracks_failures_and_closes() -> None:
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="working",
                transport=_working_provider(),
                tool="search",
            ),
            ProviderDefinition(
                identifier="broken",
                transport=_broken_provider(),
                tool="search",
            ),
        ]
    )
    assert [item.identifier for item in registry.definitions()] == ["broken", "working"]
    await registry.startup()
    await registry.ensure_started()
    assert [session.identifier for session in registry.active_sessions()] == ["working"]
    assert registry.health()["broken"].status == HealthStatus.UNHEALTHY
    await registry.close()


@pytest.mark.asyncio
async def test_registry_retries_only_unavailable_providers() -> None:
    flaky_state = {"attempts": 0}
    stable_state = {"attempts": 0}
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="flaky",
                transport=_fail_once_provider(flaky_state),
                tool="search",
            ),
            ProviderDefinition(
                identifier="stable",
                transport=_counted_provider(stable_state),
                tool="search",
            ),
        ]
    )

    await registry.startup()
    assert [session.identifier for session in registry.active_sessions()] == ["stable"]

    await registry.ensure_started({"flaky"})
    assert flaky_state["attempts"] == 2
    assert stable_state["attempts"] == 1
    assert [session.identifier for session in registry.active_sessions()] == ["flaky", "stable"]
    await registry.close()


@pytest.mark.asyncio
async def test_stalled_recovery_does_not_block_healthy_provider_results() -> None:
    state = {"attempts": 0}
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="flaky",
                transport=_fail_then_stall_provider(state),
                tool="search",
                timeout_seconds=1,
            ),
            ProviderDefinition(
                identifier="stable",
                transport=_working_provider(),
                tool="search",
            ),
        ]
    )
    await registry.startup()
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=2),
        max_results=10,
        reciprocal_rank_k=60,
    )

    try:
        response = await orchestrator.execute(SearchQuery(query="general", timeout_seconds=0.05))
        assert [result.title for result in response.results] == ["general"]
        assert response.selected_providers == ["stable"]
        assert response.timed_out_providers == []
        assert state["attempts"] == 2
    finally:
        await registry.close()


@pytest.mark.asyncio
async def test_explicit_route_uses_ready_provider_while_peer_recovers() -> None:
    state = {"attempts": 0}
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="flaky",
                transport=_fail_then_stall_provider(state),
                tool="search",
                timeout_seconds=1,
            ),
            ProviderDefinition(
                identifier="stable",
                transport=_working_provider(),
                tool="search",
            ),
        ]
    )
    await registry.startup()
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=2),
        max_results=10,
        reciprocal_rank_k=60,
    )

    try:
        response = await orchestrator.execute(
            SearchQuery(
                query="general",
                providers=["flaky", "stable"],
                timeout_seconds=0.05,
            )
        )
        assert [result.title for result in response.results] == ["general"]
        assert response.selected_providers == ["stable"]
        assert response.timed_out_providers == ["flaky"]
    finally:
        await registry.close()


@pytest.mark.asyncio
async def test_explicit_partial_route_distinguishes_completed_startup_failure() -> None:
    class SettledFailureRegistry(ProviderRegistry):
        async def ensure_started(
            self,
            required_identifiers: set[str] | None = None,
        ) -> None:
            await super().ensure_started(required_identifiers)
            for _ in range(10):
                if not self.recovering_identifiers():
                    return
                await asyncio.sleep(0)

    registry = SettledFailureRegistry(
        [
            ProviderDefinition(
                identifier="failed",
                transport=_broken_provider(),
                tool="search",
            ),
            ProviderDefinition(
                identifier="stable",
                transport=_working_provider(),
                tool="search",
            ),
        ]
    )
    await registry.startup()
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=2),
        max_results=10,
        reciprocal_rank_k=60,
    )

    try:
        response = await orchestrator.execute(
            SearchQuery(
                query="general",
                providers=["failed", "stable"],
            )
        )
        assert [result.title for result in response.results] == ["general"]
        assert [failure.model_dump() for failure in response.failed_providers] == [
            {"provider": "failed", "error_type": "RuntimeError"}
        ]
        assert response.timed_out_providers == []
    finally:
        await registry.close()


@pytest.mark.asyncio
async def test_short_required_waiter_does_not_cancel_shared_recovery() -> None:
    state = {"attempts": 0}
    release_recovery = asyncio.Event()
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="required",
                transport=_fail_then_wait_provider(state, release_recovery),
                tool="search",
            )
        ]
    )
    await registry.startup()
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )

    try:
        short_request = asyncio.create_task(
            orchestrator.execute(
                SearchQuery(query="short", providers=["required"], timeout_seconds=0.01)
            )
        )
        long_request = asyncio.create_task(
            orchestrator.execute(
                SearchQuery(query="long", providers=["required"], timeout_seconds=0.2)
            )
        )
        await asyncio.sleep(0.02)
        release_recovery.set()

        short_response = await short_request
        long_response = await long_request
        assert short_response.timed_out_providers == ["required"]
        assert [result.title for result in long_response.results] == ["long"]
        assert long_response.timed_out_providers == []
        assert state["attempts"] == 2
    finally:
        release_recovery.set()
        await registry.close()


@pytest.mark.asyncio
async def test_startup_timeout_distinguishes_failed_and_recovering_providers() -> None:
    state = {"attempts": 0}
    release_recovery = asyncio.Event()
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="failed",
                transport=_broken_provider(),
                tool="search",
            ),
            ProviderDefinition(
                identifier="recovering",
                transport=_fail_then_wait_provider(state, release_recovery),
                tool="search",
            ),
        ]
    )
    await registry.startup()
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=2),
        max_results=10,
        reciprocal_rank_k=60,
    )

    try:
        response = await orchestrator.execute(
            SearchQuery(
                query="general",
                providers=["failed", "recovering"],
                timeout_seconds=0.01,
            )
        )
        assert [failure.model_dump() for failure in response.failed_providers] == [
            {"provider": "failed", "error_type": "RuntimeError"}
        ]
        assert response.timed_out_providers == ["recovering"]
    finally:
        release_recovery.set()
        await registry.close()


@pytest.mark.asyncio
async def test_completed_startup_failure_returns_failure_response() -> None:
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="failed",
                transport=_broken_provider(),
                tool="search",
            )
        ]
    )
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )

    try:
        response = await orchestrator.execute(SearchQuery(query="general"))
        assert [failure.model_dump() for failure in response.failed_providers] == [
            {"provider": "failed", "error_type": "RuntimeError"}
        ]
        assert response.timed_out_providers == []
    finally:
        await registry.close()


@pytest.mark.asyncio
async def test_startup_and_close_detach_cancellation_suppressing_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()
    release_recovery = asyncio.Event()
    cleanup_finished = asyncio.Event()
    original_close = MCPProviderSession.close

    async def tracked_close(session: MCPProviderSession) -> None:
        await original_close(session)
        cleanup_finished.set()

    monkeypatch.setattr(MCPProviderSession, "close", tracked_close)
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="resistant",
                transport=_cancellation_suppressing_startup_provider(
                    entered,
                    release_recovery,
                ),
                tool="search",
                timeout_seconds=0.05,
            )
        ]
    )
    startup_task = asyncio.create_task(registry.startup(), name="test-registry-startup")
    await asyncio.wait_for(entered.wait(), timeout=1)
    recovery_task = next(
        task for task in asyncio.all_tasks() if task.get_name() == "search-hub-recover-resistant"
    )
    close_task: asyncio.Task[None] | None = None

    try:
        startup_done, _ = await asyncio.wait({startup_task}, timeout=0.5)
        assert startup_task in startup_done
        await startup_task
        assert registry.recovering_identifiers() == {"resistant"}

        close_task = asyncio.create_task(registry.close(), name="test-registry-close")
        done, _ = await asyncio.wait({close_task}, timeout=0.5)
        assert close_task in done
        await close_task
        assert registry.active_sessions() == []
        assert registry.recovering_identifiers() == set()
        assert registry.health() == {}
        assert recovery_task.done() is False
        assert cleanup_finished.is_set() is False
        await registry.close()
    finally:
        release_recovery.set()
        await asyncio.gather(
            recovery_task,
            startup_task,
            *([close_task] if close_task is not None else []),
            return_exceptions=True,
        )

    await asyncio.wait_for(cleanup_finished.wait(), timeout=1)
    await asyncio.sleep(0)
    assert not {
        task.get_name()
        for task in asyncio.all_tasks()
        if task.get_name() in {"search-hub-recover-resistant", "search-hub-close-resistant"}
    }


@pytest.mark.asyncio
async def test_cancelled_close_retains_deferred_recovery_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()
    release_recovery = asyncio.Event()
    cleanup_finished = asyncio.Event()
    original_close = MCPProviderSession.close

    async def tracked_close(session: MCPProviderSession) -> None:
        await original_close(session)
        cleanup_finished.set()

    monkeypatch.setattr(MCPProviderSession, "close", tracked_close)
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="resistant",
                transport=_cancellation_suppressing_startup_provider(
                    entered,
                    release_recovery,
                ),
                tool="search",
                timeout_seconds=30,
            )
        ]
    )
    recovery_waiter = asyncio.create_task(
        registry.ensure_started({"resistant"}),
        name="test-recovery-waiter",
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    recovery_task = next(
        task for task in asyncio.all_tasks() if task.get_name() == "search-hub-recover-resistant"
    )
    close_task = asyncio.create_task(registry.close(), name="test-registry-close")

    try:
        for _ in range(100):
            if recovery_task.cancelling():
                break
            await asyncio.sleep(0.001)
        assert recovery_task.cancelling()
        close_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await close_task
        assert registry.active_sessions() == []
        assert registry.recovering_identifiers() == set()
    finally:
        release_recovery.set()
        await asyncio.gather(
            recovery_task,
            recovery_waiter,
            close_task,
            return_exceptions=True,
        )

    await asyncio.wait_for(cleanup_finished.wait(), timeout=1)
    await asyncio.sleep(0)
    assert not {
        task.get_name()
        for task in asyncio.all_tasks()
        if task.get_name() in {"search-hub-recover-resistant", "search-hub-close-resistant"}
    }


@pytest.mark.asyncio
async def test_close_detaches_cancellation_suppressing_session_teardown() -> None:
    teardown_entered = asyncio.Event()
    release_teardown = asyncio.Event()
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="resistant",
                transport=_cancellation_suppressing_teardown_provider(
                    teardown_entered,
                    release_teardown,
                ),
                tool="search",
            )
        ]
    )
    await registry.startup()
    close_task = asyncio.create_task(registry.close(), name="test-registry-close")
    detached_cleanup: list[asyncio.Task[object]] = []

    try:
        await asyncio.wait_for(teardown_entered.wait(), timeout=1)
        done, _ = await asyncio.wait({close_task}, timeout=0.5)
        assert close_task in done
        await close_task
        assert registry.active_sessions() == []
        assert registry.health() == {}
        detached_cleanup = [
            task for task in asyncio.all_tasks() if task.get_name() == "search-hub-close-resistant"
        ]
        assert len(detached_cleanup) == 1
    finally:
        release_teardown.set()
        await asyncio.gather(
            close_task,
            *detached_cleanup,
            return_exceptions=True,
        )

    await asyncio.sleep(0)
    assert not {
        task.get_name()
        for task in asyncio.all_tasks()
        if task.get_name() == "search-hub-close-resistant"
    }


@pytest.mark.asyncio
async def test_provider_startup_honors_provider_timeout() -> None:
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="stalled",
                transport=_stalled_provider(),
                tool="search",
                timeout_seconds=0.01,
            )
        ]
    )
    started = time.perf_counter()
    await registry.startup()
    assert time.perf_counter() - started < 0.2
    assert registry.active_sessions() == []
    assert registry.health()["stalled"].status == HealthStatus.UNHEALTHY
    await registry.close()
    assert registry.active_sessions() == []
    await registry.close()


@pytest.mark.asyncio
async def test_provider_call_timeout_updates_health() -> None:
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="slow",
                transport=_slow_search_provider(),
                tool="search",
                timeout_seconds=0.01,
            )
        ]
    )
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )
    response = await orchestrator.execute(SearchQuery(query="general", timeout_seconds=0.1))
    assert response.timed_out_providers == ["slow"]
    health = registry.health()["slow"]
    assert health.status == HealthStatus.UNHEALTHY
    assert health.message == "TimeoutError"
    assert health.consecutive_failures == 1
    await registry.close()


@pytest.mark.asyncio
async def test_late_completion_cannot_erase_global_timeout_health() -> None:
    state = {"delay": 0.05}
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="late",
                transport=_cancellation_resistant_provider(state),
                tool="search",
                timeout_seconds=1,
            )
        ]
    )
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )
    response = await orchestrator.execute(SearchQuery(query="general", timeout_seconds=0.01))
    assert response.timed_out_providers == ["late"]
    immediate_health = registry.health()["late"]
    assert immediate_health.status == HealthStatus.UNHEALTHY
    assert 5 <= (immediate_health.latency_ms or 0) < 30

    await asyncio.sleep(0.05)
    late_health = registry.health()["late"]
    assert late_health.status == HealthStatus.UNHEALTHY
    assert late_health.consecutive_failures == 1

    state["delay"] = 0
    recovered = await orchestrator.execute(SearchQuery(query="general", timeout_seconds=0.1))
    assert [result.title for result in recovered.results] == ["general"]
    assert registry.health()["late"].status == HealthStatus.HEALTHY
    await registry.close()


@pytest.mark.asyncio
async def test_provider_cap_is_not_extended_by_cancellation_resistant_call() -> None:
    state = {"delay": 0.05}
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="resistant",
                transport=_cancellation_resistant_provider(state),
                tool="search",
                timeout_seconds=0.01,
            )
        ]
    )
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )
    started = time.perf_counter()
    response = await orchestrator.execute(SearchQuery(query="general", timeout_seconds=0.1))
    assert time.perf_counter() - started < 0.04
    assert response.timed_out_providers == ["resistant"]
    health = registry.health()["resistant"]
    assert health.status == HealthStatus.UNHEALTHY
    assert 5 <= (health.latency_ms or 0) < 30

    await asyncio.sleep(0.05)
    assert registry.health()["resistant"].status == HealthStatus.UNHEALTHY
    await registry.close()


@pytest.mark.asyncio
async def test_repeated_timeouts_do_not_overlap_provider_work() -> None:
    state = {"active": 0, "started": 0, "max_active": 0}
    finish = asyncio.Event()
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="bounded",
                transport=_blocking_provider(state, finish),
                tool="search",
                timeout_seconds=0.01,
            )
        ]
    )
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )

    try:
        responses = [
            await orchestrator.execute(SearchQuery(query="general", timeout_seconds=0.05))
            for _ in range(3)
        ]
        assert all(response.timed_out_providers == ["bounded"] for response in responses)
        assert state["active"] == 1
        assert state["max_active"] == 1
    finally:
        finish.set()
        await asyncio.sleep(0.05)
        await registry.close()


@pytest.mark.asyncio
async def test_cancelled_request_quarantines_cancellation_resistant_provider() -> None:
    state = {"active": 0, "started": 0, "max_active": 0}
    finish = asyncio.Event()
    registry = ProviderRegistry(
        [
            ProviderDefinition(
                identifier="bounded",
                transport=_blocking_provider(state, finish),
                tool="search",
                timeout_seconds=1,
            )
        ]
    )
    orchestrator = SearchOrchestrator(
        registry=registry,
        planner=RoutingPlanner(max_providers=1),
        max_results=10,
        reciprocal_rank_k=60,
    )
    request = asyncio.create_task(
        orchestrator.execute(SearchQuery(query="cancelled", timeout_seconds=1))
    )

    try:
        for _ in range(100):
            if state["started"]:
                break
            await asyncio.sleep(0.001)
        assert state["started"] == 1

        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert registry.active_sessions() == []
        assert registry.health()["bounded"].status == HealthStatus.UNHEALTHY

        response = await orchestrator.execute(
            SearchQuery(query="must-not-overlap", timeout_seconds=0.05)
        )
        assert response.timed_out_providers == ["bounded"]
        assert state["max_active"] == 1
    finally:
        finish.set()
        await asyncio.sleep(0.05)
        await registry.close()


def test_registry_builds_generic_definitions_from_settings() -> None:
    settings = AppSettings(
        providers={
            "remote": ProviderSettings(
                transport="https://provider.example/mcp",
                tool="lookup",
                tags={"technical"},
                static_arguments={"language": "en"},
            ),
            "disabled": ProviderSettings(enabled=False),
        }
    )
    registry = ProviderRegistry.from_settings(settings)
    definitions = registry.definitions()
    assert len(definitions) == 1
    assert definitions[0].identifier == "remote"
    assert definitions[0].tool == "lookup"
    assert definitions[0].static_arguments == {"language": "en"}
