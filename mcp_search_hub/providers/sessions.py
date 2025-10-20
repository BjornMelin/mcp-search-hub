"""Provider session implementations backed by FastMCP clients."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from fastmcp.client.client import CallToolResult, Client

from ..models import HealthStatus, ProviderHealth, SearchQuery

logger = logging.getLogger(__name__)


class ProviderSession(Protocol):
    """Protocol implemented by all provider client sessions."""

    identifier: str
    tags: set[str]
    weight: float
    default_tool: str
    timeout: float

    async def start(self) -> None:
        """Establish any underlying transport connections."""

    async def call_search(self, query: SearchQuery) -> tuple[CallToolResult, float]:
        """Execute a search query and return the MCP call result with latency."""

    async def close(self) -> None:
        """Release underlying resources."""

    def health(self) -> ProviderHealth:
        """Return the current health snapshot for observability."""


@dataclass(slots=True)
class ProviderDefinition:  # pylint: disable=too-many-instance-attributes
    """Descriptor used to instantiate provider sessions."""

    identifier: str
    transport: Any
    tool: str
    title: str | None = None
    tags: set[str] = field(default_factory=set)
    weight: float = 1.0
    timeout: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)
    failure_threshold: int = 3


class MCPProviderSession:
    """Provider session built on top of :class:`fastmcp.client.Client`."""

    def __init__(self, definition: ProviderDefinition):
        self._definition = definition
        self._client = Client(
            definition.transport,
            name=f"hub-{definition.identifier}",
            timeout=definition.timeout,
        )
        self._health = ProviderHealth(
            identifier=definition.identifier,
            status=HealthStatus.DEGRADED,
            message="Session not started",
            latency_ms=None,
            consecutive_failures=0,
        )
        self._lock = asyncio.Lock()
        self._connected = False

    @property
    def definition(self) -> ProviderDefinition:
        """Return the provider definition used by this session."""

        return self._definition

    @property
    def identifier(self) -> str:
        """Return the provider identifier."""

        return self._definition.identifier

    @property
    def tags(self) -> set[str]:
        """Return the provider tags used for routing."""

        return set(self._definition.tags)

    @property
    def weight(self) -> float:
        """Return the provider selection weight."""

        return self._definition.weight

    @property
    def default_tool(self) -> str:
        """Return the primary tool invoked for search queries."""

        return self._definition.tool

    @property
    def timeout(self) -> float:
        """Return the timeout applied to tool invocations."""

        return self._definition.timeout

    async def start(self) -> None:
        """Establish the underlying MCP connection lazily."""

        async with self._lock:
            if self._connected:
                return
            await self._client.__aenter__()  # pylint: disable=unnecessary-dunder-call
            self._connected = True
            self._health.status = HealthStatus.HEALTHY
            self._health.message = "Connected"
            self._health.consecutive_failures = 0

    async def call_search(self, query: SearchQuery) -> tuple[CallToolResult, float]:
        """Call the provider's primary tool with the serialized query payload."""

        if not self._connected:
            await self.start()

        payload = {
            "query": query.query,
            "max_results": query.max_results,
            "include_raw_content": query.include_raw_content,
            "advanced": query.advanced,
            "tags": sorted(query.tags),
        }

        start = time.perf_counter()
        try:
            result = await self._client.call_tool(
                self.default_tool,
                arguments=payload,
                timeout=self.timeout,
            )
        except Exception as exc:  # noqa: BLE001 - propagate after logging
            latency_ms = (time.perf_counter() - start) * 1000.0
            self._register_failure(exc, latency_ms)
            raise

        latency_ms = (time.perf_counter() - start) * 1000.0
        self._register_success(latency_ms)
        return result, latency_ms

    async def close(self) -> None:
        """Close the underlying MCP client session."""

        async with self._lock:
            if not self._connected:
                return
            await self._client.__aexit__(None, None, None)
            self._connected = False
            self._health.status = HealthStatus.DEGRADED
            self._health.message = "Disconnected"

    def health(self) -> ProviderHealth:
        """Return the latest provider health snapshot."""

        return self._health.model_copy()

    def _register_success(self, latency_ms: float) -> None:
        self._health.latency_ms = latency_ms
        self._health.consecutive_failures = 0
        self._health.status = HealthStatus.HEALTHY
        self._health.message = "OK"

    def _register_failure(self, error: Exception, latency_ms: float) -> None:
        self._health.latency_ms = latency_ms
        self._health.consecutive_failures += 1
        threshold = max(1, self.definition.failure_threshold)
        if self._health.consecutive_failures >= threshold:
            self._health.status = HealthStatus.UNHEALTHY
        else:
            self._health.status = HealthStatus.DEGRADED
        self._health.message = str(error)
        logger.warning(
            "Provider %s failure (%s/%s): %s",
            self.identifier,
            self._health.consecutive_failures,
            threshold,
            error,
            exc_info=error if logger.isEnabledFor(logging.DEBUG) else None,
        )


__all__ = [
    "MCPProviderSession",
    "ProviderDefinition",
    "ProviderSession",
]
