"""Generic provider sessions backed by FastMCP clients."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from decimal import Decimal
from typing import Any, Protocol, cast

from fastmcp import Client
from fastmcp.client.client import CallToolResult
from fastmcp.exceptions import ToolError

from ..models import (
    HealthStatus,
    ProviderHealth,
    ProviderItem,
    ProviderResponse,
    SearchQuery,
)

logger = logging.getLogger(__name__)


class ProviderSession(Protocol):
    """Minimal contract used by routing and orchestration."""

    @property
    def identifier(self) -> str: ...

    @property
    def tags(self) -> set[str]: ...

    @property
    def weight(self) -> float: ...

    @property
    def timeout_seconds(self) -> float: ...

    @property
    def estimated_cost_usd(self) -> Decimal: ...

    @property
    def ready(self) -> bool: ...

    async def start(self) -> None: ...

    def begin_call(self) -> int: ...

    async def call_search(self, query: SearchQuery, operation_id: int) -> ProviderResponse: ...

    async def close(self) -> None: ...

    def health(self) -> ProviderHealth: ...

    def record_timeout(self, operation_id: int) -> None: ...


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    """Resolved data required to invoke and normalize one provider."""

    identifier: str
    transport: Any
    tool: str
    tags: frozenset[str] = field(default_factory=lambda: frozenset[str]())
    weight: float = 1.0
    timeout_seconds: float = 20.0
    estimated_cost_usd: Decimal = Decimal("0")
    query_argument: str = "query"
    max_results_argument: str | None = "max_results"
    raw_content_argument: str | None = "include_raw_content"
    static_arguments: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    result_path: tuple[str | int, ...] = ("results",)
    field_aliases: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict[str, tuple[str, ...]]()
    )


class MCPProviderSession:
    """One lifecycle-managed downstream MCP client."""

    def __init__(self, definition: ProviderDefinition) -> None:
        self.definition = definition
        self._client: Client[Any] = self._new_client()
        self._connected = False
        self._requires_reconnect = False
        self._lifecycle_lock = asyncio.Lock()
        self._generation = 0
        self._operation_sequence = 0
        self._active_operations: set[int] = set()
        self._operation_started: dict[int, float] = {}
        self._operation_generations: dict[int, int] = {}
        self._operation_tasks: dict[int, asyncio.Task[Any]] = {}
        self._timed_out_operations: set[int] = set()
        self._health = ProviderHealth(
            identifier=definition.identifier,
            status=HealthStatus.DEGRADED,
            message="not started",
        )

    @property
    def identifier(self) -> str:
        return self.definition.identifier

    @property
    def tags(self) -> set[str]:
        return set(self.definition.tags)

    @property
    def weight(self) -> float:
        return self.definition.weight

    @property
    def timeout_seconds(self) -> float:
        return self.definition.timeout_seconds

    @property
    def estimated_cost_usd(self) -> Decimal:
        return self.definition.estimated_cost_usd

    @property
    def ready(self) -> bool:
        return self._connected and not self._requires_reconnect

    async def start(self) -> None:
        """Connect and initialize the downstream server."""

        async with self._lifecycle_lock:
            if self.ready:
                return
            started = time.perf_counter()
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    if self._requires_reconnect:
                        await self._reset_client()
                    await self._client.__aenter__()
            except asyncio.CancelledError:
                self._requires_reconnect = True
                self._register_failure(RuntimeError("startup cancelled"), started)
                raise
            except Exception as exc:
                self._requires_reconnect = True
                self._register_failure(exc, started)
                raise
            self._connected = True
            self._requires_reconnect = False
            self._register_success(started)

    def _new_client(self) -> Client[Any]:
        return Client(
            self.definition.transport,
            name=f"search-hub-{self.definition.identifier}",
            timeout=None,
        )

    async def _reset_client(self) -> None:
        running = {
            task
            for operation_id, task in self._operation_tasks.items()
            if self._operation_generations.get(operation_id) == self._generation and not task.done()
        }
        for task in running:
            task.cancel()
        if running:
            await asyncio.wait(running)
        was_connected = self._connected
        try:
            await self._client.close()
        except Exception:
            if was_connected:
                raise
        self._connected = False
        self._client = self._new_client()
        self._generation += 1

    def begin_call(self) -> int:
        """Register one provider call and return its session-local identity."""

        self._operation_sequence += 1
        operation_id = self._operation_sequence
        self._active_operations.add(operation_id)
        self._operation_started[operation_id] = time.perf_counter()
        self._operation_generations[operation_id] = self._generation
        return operation_id

    def _discard_operation(self, operation_id: int) -> None:
        self._active_operations.discard(operation_id)
        self._operation_started.pop(operation_id, None)
        self._operation_generations.pop(operation_id, None)
        self._operation_tasks.pop(operation_id, None)
        self._timed_out_operations.discard(operation_id)

    async def call_search(self, query: SearchQuery, operation_id: int) -> ProviderResponse:
        """Invoke the configured tool and normalize its declared result shape."""

        if not self._connected:
            self._discard_operation(operation_id)
            raise RuntimeError(f"Provider {self.identifier!r} is not connected")
        if self._requires_reconnect:
            self._discard_operation(operation_id)
            raise RuntimeError(f"Provider {self.identifier!r} requires reconnect")
        if operation_id not in self._active_operations:
            raise RuntimeError(f"Provider operation {operation_id} is not registered")
        if self._operation_generations.get(operation_id) != self._generation:
            self._discard_operation(operation_id)
            raise RuntimeError(
                f"Provider operation {operation_id} belongs to a stale client generation"
            )
        operation_task = asyncio.current_task()
        if operation_task is None:
            self._discard_operation(operation_id)
            raise RuntimeError("Provider calls require an asyncio task")
        self._operation_tasks[operation_id] = operation_task
        arguments = dict(self.definition.static_arguments)
        arguments[self.definition.query_argument] = query.query
        if self.definition.max_results_argument is not None:
            arguments[self.definition.max_results_argument] = query.max_results
        if self.definition.raw_content_argument is not None:
            arguments[self.definition.raw_content_argument] = query.include_raw_content

        started = time.perf_counter()
        try:
            result = await self._client.call_tool(
                self.definition.tool,
                arguments=arguments,
                timeout=None,
            )
        except Exception as exc:
            if not isinstance(exc, ToolError):
                self._requires_reconnect = True
            self._register_failure(exc, started, operation_id)
            raise
        else:
            latency_ms = self._register_success(started, operation_id)
            return ProviderResponse(
                provider=self.identifier,
                latency_ms=latency_ms,
                results=self._normalize_results(result, query),
            )
        finally:
            self._discard_operation(operation_id)

    async def close(self) -> None:
        """Close the downstream client and mark the session unavailable."""

        async with self._lifecycle_lock:
            started = time.perf_counter()
            try:
                if self._connected or self._requires_reconnect:
                    async with asyncio.timeout(self.timeout_seconds):
                        await self._client.close()
            except Exception as exc:
                self._register_failure(exc, started)
                raise
            finally:
                self._connected = False
                self._requires_reconnect = False
                self._active_operations.clear()
                self._operation_started.clear()
                self._operation_generations.clear()
                self._operation_tasks.clear()
                self._timed_out_operations.clear()
            self._health.status = HealthStatus.DEGRADED
            self._health.message = "stopped"

    def health(self) -> ProviderHealth:
        return self._health.model_copy()

    def record_timeout(self, operation_id: int) -> None:
        """Record a timeout enforced by the orchestrator."""

        if (
            operation_id not in self._active_operations
            or operation_id in self._timed_out_operations
        ):
            return
        self._timed_out_operations.add(operation_id)
        if self._operation_generations.get(operation_id) != self._generation:
            self._discard_operation(operation_id)
            return
        self._requires_reconnect = True
        self._health.status = HealthStatus.UNHEALTHY
        self._health.message = "TimeoutError"
        self._health.latency_ms = (
            time.perf_counter() - self._operation_started[operation_id]
        ) * 1000
        self._health.consecutive_failures += 1
        if operation_id not in self._operation_tasks:
            self._discard_operation(operation_id)

    def _normalize_results(
        self, call_result: CallToolResult, query: SearchQuery
    ) -> list[ProviderItem]:
        payload: Any = _result_payload(call_result, self.definition.result_path)
        items: list[Any] = cast(list[Any], payload) if isinstance(payload, list) else [payload]
        normalized: list[ProviderItem] = []
        for provider_rank, value in enumerate(items, start=1):
            item = self._normalize_item(
                value,
                query.include_raw_content,
                provider_rank,
            )
            if item is None:
                continue
            normalized.append(item)
            if len(normalized) == query.max_results:
                break
        return normalized

    def _normalize_item(
        self,
        value: Any,
        include_raw_content: bool,
        provider_rank: int,
    ) -> ProviderItem | None:
        if isinstance(value, str):
            return ProviderItem(
                title=value[:120],
                snippet=value,
                provider_rank=provider_rank,
            )
        if not isinstance(value, dict):
            return None
        mapping = cast(dict[str, Any], value)

        def take(field_name: str) -> Any:
            for alias in self.definition.field_aliases.get(field_name, (field_name,)):
                if alias not in mapping:
                    continue
                candidate = mapping[alias]
                if candidate is None or (isinstance(candidate, str) and not candidate.strip()):
                    continue
                return candidate
            return None

        title = _optional_text(take("title")) or ""
        url = _optional_text(take("url"))
        snippet = _optional_text(take("snippet"))
        raw_content_value = take("raw_content")
        raw_content = _optional_text(raw_content_value) if include_raw_content else None
        original_score = _optional_float(take("score"))
        if not title:
            title = (url or snippet or "")[:120]
        if not any((title, url, snippet, raw_content)):
            return None
        return ProviderItem(
            title=title,
            url=url,
            snippet=snippet,
            raw_content=raw_content,
            original_score=original_score,
            provider_rank=provider_rank,
        )

    def _register_success(self, started: float, operation_id: int | None = None) -> float:
        latency_ms = (time.perf_counter() - started) * 1000
        if (
            (
                operation_id is not None
                and self._operation_generations.get(operation_id) != self._generation
            )
            or operation_id in self._timed_out_operations
            or not self._connected
            or self._requires_reconnect
        ):
            return latency_ms
        self._health.status = HealthStatus.HEALTHY
        self._health.message = "ready"
        self._health.latency_ms = latency_ms
        self._health.consecutive_failures = 0
        return latency_ms

    def _register_failure(
        self, error: Exception, started: float, operation_id: int | None = None
    ) -> None:
        is_current_generation = operation_id is None or (
            self._operation_generations.get(operation_id) == self._generation
        )
        if is_current_generation and (
            operation_id is None
            or (operation_id not in self._timed_out_operations and self._connected)
        ):
            self._health.status = HealthStatus.UNHEALTHY
            self._health.message = type(error).__name__
            self._health.latency_ms = (time.perf_counter() - started) * 1000
            self._health.consecutive_failures += 1
        logger.warning("Provider %s failed: %s", self.identifier, type(error).__name__)


def _result_payload(call_result: CallToolResult, result_path: tuple[str | int, ...]) -> Any:
    roots: list[Any] = []
    if call_result.data is not None:
        roots.append(_plain_data(call_result.data))
    if call_result.structured_content is not None:
        roots.append(call_result.structured_content)
    for block in call_result.content:
        text = getattr(block, "text", None)
        if not isinstance(text, str):
            continue
        try:
            roots.append(json.loads(text))
        except json.JSONDecodeError:
            roots.append([text])

    for root in roots:
        current = root
        try:
            for segment in result_path:
                current = current[segment]
        except (KeyError, IndexError, TypeError):
            continue
        return current
    return []


def _plain_data(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


__all__ = ["MCPProviderSession", "ProviderDefinition", "ProviderSession"]
