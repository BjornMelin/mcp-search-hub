"""Generic downstream provider adapter tests."""

from __future__ import annotations

import asyncio
from collections import deque
from decimal import Decimal
from typing import Any, cast

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.client import CallToolResult
from fastmcp.exceptions import ToolError

from mcp_search_hub.models import HealthStatus, SearchQuery
from mcp_search_hub.orchestrator import fuse_results
from mcp_search_hub.providers import MCPProviderSession, ProviderDefinition


def _provider_server() -> FastMCP:
    server = FastMCP("provider")

    def lookup(term: str, count: int, raw: bool, source: str) -> dict[str, object]:
        return {
            "payload": {
                "items": [
                    {
                        "heading": f"Result for {term}",
                        "href": "https://example.test/result",
                        "body": "raw body" if raw else "summary",
                        "alternate_body": "must never leak",
                        "private_blob": "must never leak",
                        "rank_score": "Infinity" if term == "infinite" else "0.75",
                        "source": source,
                    }
                ][:count]
            }
        }

    server.tool(lookup)

    return server


def _concurrent_provider_server() -> FastMCP:
    server = FastMCP("concurrent-provider")

    async def search(query: str, max_results: int, include_raw_content: bool) -> dict[str, object]:
        delay = 0.05 if query == "late" else 0.02
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            await asyncio.sleep(0.03)
        return {
            "results": [{"title": query, "content": "body" if include_raw_content else None}][
                :max_results
            ]
        }

    server.tool(search)
    return server


@pytest.mark.asyncio
async def test_generic_provider_maps_arguments_results_and_health() -> None:
    session = MCPProviderSession(
        ProviderDefinition(
            identifier="custom",
            transport=_provider_server(),
            tool="lookup",
            tags=frozenset({"general"}),
            estimated_cost_usd=Decimal("0.02"),
            query_argument="term",
            max_results_argument="count",
            raw_content_argument="raw",
            static_arguments={"source": "hub"},
            result_path=("payload", "items"),
            field_aliases={
                "title": ("heading",),
                "url": ("href",),
                "snippet": ("body",),
                "score": ("rank_score",),
                "raw_content": ("body", "alternate_body"),
            },
        )
    )
    assert session.ready is False
    await session.start()
    assert session.health().status == HealthStatus.HEALTHY
    response = await session.call_search(
        SearchQuery(query="FastMCP", max_results=1, include_raw_content=True),
        session.begin_call(),
    )
    assert response.provider == "custom"
    assert response.results[0].title == "Result for FastMCP"
    assert response.results[0].raw_content == "raw body"
    assert response.results[0].original_score == 0.75
    assert response.results[0].metadata == {}
    without_raw = await session.call_search(
        SearchQuery(query="FastMCP", max_results=1, include_raw_content=False),
        session.begin_call(),
    )
    assert without_raw.results[0].raw_content is None
    assert without_raw.results[0].metadata == {}
    invalid_score = await session.call_search(
        SearchQuery(query="infinite", max_results=1),
        session.begin_call(),
    )
    assert invalid_score.results[0].original_score is None
    await session.close()
    assert session.ready is False


@pytest.mark.asyncio
async def test_result_aliases_fall_through_blank_primary_values() -> None:
    server = FastMCP("alias-provider")

    def search(query: str) -> dict[str, object]:
        del query
        return {
            "results": [
                {
                    "title": None,
                    "name": "Fallback title",
                    "url": " ",
                    "link": "https://example.test/fallback",
                }
            ]
        }

    server.tool(search)
    session = MCPProviderSession(
        ProviderDefinition(
            identifier="aliases",
            transport=server,
            tool="search",
            max_results_argument=None,
            raw_content_argument=None,
            field_aliases={
                "title": ("title", "name"),
                "url": ("url", "link"),
            },
        )
    )
    await session.start()

    response = await session.call_search(
        SearchQuery(query="fallback"),
        session.begin_call(),
    )
    assert response.results[0].title == "Fallback title"
    assert response.results[0].url == "https://example.test/fallback"
    await session.close()


@pytest.mark.asyncio
async def test_normalization_preserves_original_provider_rank() -> None:
    server = FastMCP("rank-provider")

    def search(query: str) -> dict[str, object]:
        del query
        return {
            "results": [
                {"ignored": []},
                {"title": "Second provider result"},
            ]
        }

    server.tool(search)
    session = MCPProviderSession(
        ProviderDefinition(
            identifier="ranked",
            transport=server,
            tool="search",
            max_results_argument=None,
            raw_content_argument=None,
        )
    )
    await session.start()
    response = await session.call_search(
        SearchQuery(query="rank", max_results=1),
        session.begin_call(),
    )

    fused = fuse_results([response], reciprocal_rank_k=60, limit=1)
    assert fused[0].sources[0].rank == 2
    assert fused[0].score == pytest.approx(1 / 62)
    assert "provider_rank" not in response.results[0].model_dump()
    await session.close()


@pytest.mark.asyncio
async def test_provider_requires_lifecycle_start() -> None:
    session = MCPProviderSession(
        ProviderDefinition(
            identifier="custom",
            transport=_provider_server(),
            tool="lookup",
        )
    )
    with pytest.raises(RuntimeError, match="not connected"):
        await session.call_search(SearchQuery(query="x"), session.begin_call())
    await session.close()


@pytest.mark.asyncio
async def test_provider_failure_updates_sanitized_health() -> None:
    server = FastMCP("broken")

    def search(query: str) -> dict[str, object]:
        raise ConnectionError(f"secret detail for {query}")

    server.tool(search)

    session = MCPProviderSession(
        ProviderDefinition(identifier="broken", transport=server, tool="search")
    )
    await session.start()
    with pytest.raises(ToolError):
        await session.call_search(SearchQuery(query="x"), session.begin_call())
    health = session.health()
    assert health.status == HealthStatus.UNHEALTHY
    assert health.message is not None
    assert "secret detail" not in health.message
    assert session.ready is True
    await session.close()


@pytest.mark.asyncio
async def test_client_failure_requires_reconnect_before_next_call() -> None:
    class ControlledClient:
        def __init__(self, *, error: Exception | None = None) -> None:
            self.error = error
            self.calls = 0

        async def __aenter__(self) -> ControlledClient:
            return self

        async def close(self) -> None:
            return None

        async def call_tool(self, *_args: object, **_kwargs: object) -> CallToolResult:
            self.calls += 1
            if self.error is not None:
                raise self.error
            return CallToolResult(
                content=[],
                structured_content={"results": [{"title": "recovered"}]},
                meta=None,
            )

    class SequencedClientSession(MCPProviderSession):
        clients: deque[ControlledClient]

        def _new_client(self) -> Client[Any]:
            return cast(Client[Any], self.clients.popleft())

    failed_client = ControlledClient(error=ConnectionError("transport failed"))
    recovered_client = ControlledClient()
    SequencedClientSession.clients = deque([failed_client, recovered_client])
    session = SequencedClientSession(
        ProviderDefinition(identifier="versioned", transport="unused", tool="search")
    )
    await session.start()

    with pytest.raises(ConnectionError, match="transport failed"):
        await session.call_search(SearchQuery(query="first"), session.begin_call())
    assert session.ready is False

    await session.start()
    response = await session.call_search(
        SearchQuery(query="second"),
        session.begin_call(),
    )
    assert response.results[0].title == "recovered"
    assert failed_client.calls == 1
    assert recovered_client.calls == 1
    await session.close()


@pytest.mark.asyncio
async def test_timeout_quarantines_session_despite_a_later_concurrent_success() -> None:
    session = MCPProviderSession(
        ProviderDefinition(
            identifier="concurrent",
            transport=_concurrent_provider_server(),
            tool="search",
        )
    )
    await session.start()
    late_operation = session.begin_call()
    late_task = asyncio.create_task(session.call_search(SearchQuery(query="late"), late_operation))
    await asyncio.sleep(0.005)
    fast_operation = session.begin_call()
    fast_task = asyncio.create_task(session.call_search(SearchQuery(query="fast"), fast_operation))
    await asyncio.sleep(0.005)
    session.record_timeout(late_operation)
    late_task.cancel()

    fast_response = await fast_task
    await asyncio.gather(late_task, return_exceptions=True)
    assert fast_response.results[0].title == "fast"
    assert session.health().status == HealthStatus.UNHEALTHY
    assert session.ready is False
    await session.close()


@pytest.mark.asyncio
async def test_stale_operation_never_invokes_recovered_client() -> None:
    calls = 0
    server = FastMCP("recovered-provider")

    def search(query: str, max_results: int, include_raw_content: bool) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "results": [{"title": query, "raw_content": query if include_raw_content else None}][
                :max_results
            ]
        }

    server.tool(search)
    session = MCPProviderSession(
        ProviderDefinition(identifier="recovered", transport=server, tool="search")
    )
    await session.start()
    stale_operation = session.begin_call()
    timed_out_operation = session.begin_call()
    session.record_timeout(timed_out_operation)
    await session.start()

    with pytest.raises(RuntimeError, match="not registered"):
        await session.call_search(SearchQuery(query="timed out"), timed_out_operation)
    with pytest.raises(RuntimeError, match="stale client generation"):
        await session.call_search(SearchQuery(query="stale"), stale_operation)
    assert calls == 0
    await session.close()


@pytest.mark.asyncio
async def test_recovery_never_overlaps_client_generations() -> None:
    active_calls = 0
    max_active_calls = 0
    old_started = asyncio.Event()
    old_cancelled = asyncio.Event()
    release_old = asyncio.Event()
    replacement_started = asyncio.Event()

    class ControlledClient:
        def __init__(self, *, old: bool) -> None:
            self.old = old

        async def __aenter__(self) -> ControlledClient:
            if not self.old:
                replacement_started.set()
            return self

        async def close(self) -> None:
            return None

        async def call_tool(self, *_args: object, **_kwargs: object) -> CallToolResult:
            nonlocal active_calls, max_active_calls
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            try:
                if self.old:
                    old_started.set()
                    try:
                        await release_old.wait()
                    except asyncio.CancelledError:
                        old_cancelled.set()
                        await release_old.wait()
                return CallToolResult(
                    content=[],
                    structured_content={"results": [{"title": "result"}]},
                    meta=None,
                )
            finally:
                active_calls -= 1

    class SequencedClientSession(MCPProviderSession):
        clients: deque[ControlledClient]

        def _new_client(self) -> Client[Any]:
            return cast(Client[Any], self.clients.popleft())

    SequencedClientSession.clients = deque(
        [ControlledClient(old=True), ControlledClient(old=False)]
    )
    session = SequencedClientSession(
        ProviderDefinition(
            identifier="versioned",
            transport="unused",
            tool="search",
            timeout_seconds=0.03,
        )
    )
    await session.start()
    old_operation = session.begin_call()
    old_call = asyncio.create_task(session.call_search(SearchQuery(query="old"), old_operation))
    await asyncio.wait_for(old_started.wait(), timeout=1)
    session.record_timeout(old_operation)

    try:
        with pytest.raises(TimeoutError):
            await session.start()
        assert old_cancelled.is_set()
        assert not replacement_started.is_set()
        assert max_active_calls == 1

        release_old.set()
        await old_call
        await session.start()
        await session.call_search(SearchQuery(query="new"), session.begin_call())
        assert replacement_started.is_set()
        assert max_active_calls == 1
    finally:
        release_old.set()
        await asyncio.gather(old_call, return_exceptions=True)
        await session.close()


@pytest.mark.parametrize(
    ("old_fails", "new_fails", "expected_status", "expected_failures"),
    [
        (False, True, HealthStatus.UNHEALTHY, 1),
        (True, False, HealthStatus.HEALTHY, 0),
    ],
)
@pytest.mark.asyncio
async def test_timed_out_completion_cannot_overwrite_recovered_health(
    old_fails: bool,
    new_fails: bool,
    expected_status: HealthStatus,
    expected_failures: int,
) -> None:
    class ControlledClient:
        def __init__(self, *, release: asyncio.Event | None = None, error: Exception | None = None):
            self.release = release
            self.error = error

        async def __aenter__(self) -> ControlledClient:
            return self

        async def close(self) -> None:
            return None

        async def call_tool(self, *_args: object, **_kwargs: object) -> CallToolResult:
            if self.release is not None:
                await self.release.wait()
            if self.error is not None:
                raise self.error
            return CallToolResult(
                content=[],
                structured_content={"results": [{"title": "old result"}]},
                meta=None,
            )

    class SequencedClientSession(MCPProviderSession):
        clients: deque[ControlledClient]

        def _new_client(self) -> Client[Any]:
            return cast(Client[Any], self.clients.popleft())

    release_old_call = asyncio.Event()
    SequencedClientSession.clients = deque(
        [
            ControlledClient(
                release=release_old_call,
                error=RuntimeError("old generation failed") if old_fails else None,
            ),
            ControlledClient(error=RuntimeError("new generation failed") if new_fails else None),
        ]
    )
    session = SequencedClientSession(
        ProviderDefinition(identifier="versioned", transport="unused", tool="search")
    )
    await session.start()

    old_operation = session.begin_call()
    old_call = asyncio.create_task(session.call_search(SearchQuery(query="old"), old_operation))
    await asyncio.sleep(0)
    session.record_timeout(old_operation)
    release_old_call.set()
    if old_fails:
        with pytest.raises(RuntimeError, match="old generation failed"):
            await old_call
    else:
        await old_call

    await session.start()
    new_call = session.call_search(SearchQuery(query="new"), session.begin_call())
    if new_fails:
        with pytest.raises(RuntimeError, match="new generation failed"):
            await new_call
    else:
        await new_call
    assert session.health().status == expected_status
    assert session.health().consecutive_failures == expected_failures
    await session.close()
