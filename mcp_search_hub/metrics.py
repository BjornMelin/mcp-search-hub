"""Metrics helpers for tracking orchestrator performance."""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass
class MetricsSnapshot:
    """Serializable metrics payload exposed through `/metrics`."""

    total_queries: int
    total_successes: int
    total_failures: int
    cache_hits: int
    avg_latency_ms: float
    provider_usage: dict[str, int]
    last_updated: float


class MetricsTracker:
    """In-memory metrics aggregator with asyncio coordination."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._total_queries = 0
        self._total_successes = 0
        self._total_failures = 0
        self._cache_hits = 0
        self._total_latency_ms = 0.0
        self._provider_usage: Counter[str] = Counter()
        self._last_updated = time.time()

    async def record_success(
        self, provider_ids: Iterable[str], latency_ms: float, *, cache_hit: bool
    ) -> None:
        async with self._lock:
            self._total_queries += 1
            self._total_successes += 1
            if cache_hit:
                self._cache_hits += 1
            self._total_latency_ms += latency_ms
            self._provider_usage.update(provider_ids)
            self._last_updated = time.time()

    async def record_failure(self, provider_ids: Iterable[str]) -> None:
        async with self._lock:
            self._total_queries += 1
            self._total_failures += 1
            self._provider_usage.update(provider_ids)
            self._last_updated = time.time()

    async def record_cache_hit(self) -> None:
        async with self._lock:
            self._cache_hits += 1
            self._last_updated = time.time()

    def snapshot(self) -> MetricsSnapshot:
        avg_latency = 0.0
        if self._total_successes:
            avg_latency = self._total_latency_ms / self._total_successes
        return MetricsSnapshot(
            total_queries=self._total_queries,
            total_successes=self._total_successes,
            total_failures=self._total_failures,
            cache_hits=self._cache_hits,
            avg_latency_ms=avg_latency,
            provider_usage=dict(self._provider_usage),
            last_updated=self._last_updated,
        )


__all__ = ["MetricsSnapshot", "MetricsTracker"]
