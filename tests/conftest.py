"""Shared test fixtures for the refactored MCP Search Hub."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import pytest
from fastmcp.client.client import CallToolResult

from mcp_search_hub.models import HealthStatus, ProviderHealth, SearchQuery


@dataclass
class StubCall:
    provider: str
    results: list[dict[str, Any]]
    latency_ms: float = 10.0

    def to_result(self) -> CallToolResult:
        return CallToolResult(
            content=[],
            structured_content=None,
            data={"results": self.results},
            is_error=False,
        )


class StubProviderSession:
    """Lightweight provider session for orchestrator tests."""

    def __init__(self, identifier: str, tags: Iterable[str], responses: list[StubCall]):
        self.identifier = identifier
        self.tags = set(tags)
        self.weight = 1.0
        self.default_tool = "search"
        self.timeout = 5.0
        self._responses = asyncio.Queue()
        for response in responses:
            self._responses.put_nowait(response)
        self._started = False
        self.invocations = 0
        self._health = ProviderHealth(
            identifier=identifier,
            status=HealthStatus.HEALTHY,
            message="ready",
            latency_ms=None,
            consecutive_failures=0,
        )

    async def start(self) -> None:
        self._started = True

    async def call_search(self, query: SearchQuery):
        if not self._started:
            await self.start()
        response: StubCall = await self._responses.get()
        self.invocations += 1
        return response.to_result(), response.latency_ms

    async def close(self) -> None:
        self._started = False

    def health(self) -> ProviderHealth:
        return self._health.model_copy()


class StubRegistry:
    """Registry that exposes a static provider set."""

    def __init__(self, sessions: list[StubProviderSession]):
        self._sessions = sessions
        self._started = False
        self._definitions = []

    async def startup(self) -> None:
        self._started = True
        for session in self._sessions:
            await session.start()

    async def ensure_started(self) -> None:
        if not self._started:
            await self.startup()

    def active_sessions(self) -> list[StubProviderSession]:
        return self._sessions

    def definitions(self):  # pragma: no cover - patched by server tests
        return self._definitions

    def health(self) -> dict[str, ProviderHealth]:
        return {session.identifier: session.health() for session in self._sessions}

    async def close(self) -> None:
        for session in self._sessions:
            await session.close()
        self._started = False


@pytest.fixture
def stub_sessions() -> list[StubProviderSession]:
    alpha = StubProviderSession(
        "alpha",
        tags={"general"},
        responses=[
            StubCall(
                provider="alpha",
                results=[
                    {
                        "title": "Alpha Result",
                        "url": "https://alpha.example",
                        "score": 0.5,
                    }
                ],
                latency_ms=12.0,
            )
        ],
    )
    beta = StubProviderSession(
        "beta",
        tags={"code"},
        responses=[
            StubCall(
                provider="beta",
                results=[
                    {
                        "title": "Beta Result",
                        "url": "https://beta.example",
                        "score": 0.9,
                    }
                ],
                latency_ms=8.0,
            )
        ],
    )
    return [alpha, beta]


@pytest.fixture
def stub_registry(stub_sessions: list[StubProviderSession]) -> StubRegistry:
    return StubRegistry(stub_sessions)
