"""Shared deterministic provider doubles."""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal

import pytest

from mcp_search_hub.models import (
    HealthStatus,
    ProviderHealth,
    ProviderItem,
    ProviderResponse,
    SearchQuery,
)
from mcp_search_hub.providers import ProviderDefinition, ProviderSession


class StubProviderSession:
    """Provider double with configurable delay, response, and failure."""

    def __init__(
        self,
        identifier: str,
        *,
        tags: set[str] | None = None,
        weight: float = 1.0,
        cost: str = "0",
        timeout_seconds: float = 5.0,
        results: list[ProviderItem] | None = None,
        delay: float = 0.0,
        error: Exception | None = None,
    ) -> None:
        self.identifier = identifier
        self.tags = tags or set()
        self.weight = weight
        self.estimated_cost_usd = Decimal(cost)
        self.timeout_seconds = timeout_seconds
        self.ready = False
        self.results = results or []
        self.delay = delay
        self.error = error
        self.invocations = 0
        self.last_max_results: int | None = None
        self.timeout_count = 0
        self.last_timeout_seconds: float | None = None
        self._operation_sequence = 0
        self._operation_started: dict[int, float] = {}
        self._timed_out_operations: set[int] = set()

    async def start(self) -> None:
        self.ready = True

    def begin_call(self) -> int:
        self._operation_sequence += 1
        self._operation_started[self._operation_sequence] = time.perf_counter()
        return self._operation_sequence

    async def call_search(self, query: SearchQuery, operation_id: int) -> ProviderResponse:
        del operation_id
        self.invocations += 1
        self.last_max_results = query.max_results
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return ProviderResponse(
            provider=self.identifier,
            latency_ms=self.delay * 1000,
            results=self.results[: query.max_results],
        )

    async def close(self) -> None:
        self.ready = False

    def health(self) -> ProviderHealth:
        if self.timeout_count:
            return ProviderHealth(
                identifier=self.identifier,
                status=HealthStatus.UNHEALTHY,
                message="TimeoutError",
                latency_ms=(self.last_timeout_seconds or 0) * 1000,
                consecutive_failures=self.timeout_count,
            )
        return ProviderHealth(
            identifier=self.identifier,
            status=HealthStatus.HEALTHY if self.ready else HealthStatus.DEGRADED,
            message="ready" if self.ready else "stopped",
        )

    def record_timeout(self, operation_id: int) -> None:
        if operation_id in self._timed_out_operations:
            return
        self._timed_out_operations.add(operation_id)
        self.timeout_count += 1
        self.last_timeout_seconds = time.perf_counter() - self._operation_started[operation_id]


class StubRegistry:
    """Lifecycle-aware registry double."""

    def __init__(self, sessions: list[StubProviderSession]) -> None:
        self.sessions = sessions
        self.started = False
        self._definitions = [
            ProviderDefinition(
                identifier=session.identifier,
                transport="memory://unused",
                tool="search",
                tags=frozenset(session.tags),
                weight=session.weight,
                timeout_seconds=session.timeout_seconds,
                estimated_cost_usd=session.estimated_cost_usd,
            )
            for session in sessions
        ]

    async def startup(self) -> None:
        await asyncio.gather(*(session.start() for session in self.sessions))
        self.started = True

    async def ensure_started(self, required_identifiers: set[str] | None = None) -> None:
        del required_identifiers
        if not self.started:
            await self.startup()

    def active_sessions(self) -> list[ProviderSession]:
        return [session for session in self.sessions if session.ready]

    def definitions(self) -> list[ProviderDefinition]:
        return self._definitions

    def recovering_identifiers(self) -> set[str]:
        return {session.identifier for session in self.sessions if not session.ready}

    def health(self) -> dict[str, ProviderHealth]:
        return {session.identifier: session.health() for session in self.sessions}

    async def close(self) -> None:
        await asyncio.gather(*(session.close() for session in self.sessions))
        self.started = False


@pytest.fixture
def alpha_result() -> ProviderItem:
    return ProviderItem(
        title="Alpha documentation",
        url="https://example.com/docs?utm_source=test",
        snippet="Alpha",
        original_score=0.9,
    )


@pytest.fixture
def stub_registry(alpha_result: ProviderItem) -> StubRegistry:
    return StubRegistry(
        [
            StubProviderSession(
                "alpha",
                tags={"general", "technical"},
                cost="0.01",
                results=[alpha_result],
            )
        ]
    )
