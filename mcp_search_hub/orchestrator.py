"""Concurrent provider execution and reciprocal-rank fusion."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import (
    CombinedSearchResponse,
    HealthStatus,
    ProviderExecution,
    ProviderFailure,
    ProviderResponse,
    ResultSource,
    SearchQuery,
    SearchResult,
)
from .providers import ProviderRegistryProtocol, ProviderSession
from .routing import RoutingPlanner

logger = logging.getLogger(__name__)
_CANCELLATION_GRACE_SECONDS = 0.25
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid"}


class SearchOrchestrator:
    """Own provider concurrency, all request timeouts, and result fusion."""

    def __init__(
        self,
        *,
        registry: ProviderRegistryProtocol,
        planner: RoutingPlanner,
        max_results: int,
        reciprocal_rank_k: int,
    ) -> None:
        self._registry = registry
        self._planner = planner
        self._max_results = max(1, max_results)
        self._reciprocal_rank_k = max(1, reciprocal_rank_k)
        self._cleanup_tasks: set[asyncio.Task[Any]] = set()

    async def execute(self, query: SearchQuery) -> CombinedSearchResponse:
        """Execute provider startup, calls, and cancellation within one deadline."""

        started = time.perf_counter()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + query.timeout_seconds
        tasks: dict[asyncio.Task[ProviderResponse], tuple[ProviderSession, int]] = {}
        configured_costs = {
            definition.identifier: definition.estimated_cost_usd
            for definition in self._registry.definitions()
        }
        lifecycle_candidates = self._planner.validate_request(query, configured_costs)
        try:
            async with asyncio.timeout_at(deadline):
                await self._registry.ensure_started(lifecycle_candidates)
            active_sessions = self._registry.active_sessions()
            active_identifiers = {session.identifier for session in active_sessions}
            if lifecycle_candidates and not active_identifiers.intersection(lifecycle_candidates):
                return self._unavailable_response(query, lifecycle_candidates, started)
            plan = self._planner.plan(
                query,
                active_sessions,
                configured_costs=configured_costs,
            )
            unavailable_requested = set(query.providers or ()) - {
                session.identifier for session in active_sessions
            }
            startup_timeouts, startup_failures = self._classify_unavailable(unavailable_requested)
            provider_query = query.model_copy(
                update={"max_results": min(query.max_results, self._max_results)}
            )
            operations = [(session, session.begin_call()) for session in plan.providers]
            tasks = {
                asyncio.create_task(self._call_provider(session, provider_query, operation_id)): (
                    session,
                    operation_id,
                )
                for session, operation_id in operations
            }
            done, pending = await asyncio.wait(
                tasks,
                timeout=max(0.0, deadline - loop.time()),
            )
        except TimeoutError:
            await self._cancel_and_drain(set(tasks), timeout_seconds=0.0)
            return self._unavailable_response(query, lifecycle_candidates, started)
        except asyncio.CancelledError:
            await self._cancel_and_drain(
                set(tasks),
                timeout_seconds=_CANCELLATION_GRACE_SECONDS,
            )
            raise

        for task in pending:
            session, operation_id = tasks[task]
            session.record_timeout(operation_id)
        timed_out = startup_timeouts | {tasks[task][0].identifier for task in pending}
        await self._cancel_and_drain(pending, timeout_seconds=0.0)

        successful: list[ProviderResponse] = []
        failures = startup_failures
        for task in sorted(done, key=lambda item: tasks[item][0].identifier):
            identifier = tasks[task][0].identifier
            try:
                successful.append(task.result())
            except TimeoutError:
                timed_out.add(identifier)
            except Exception as exc:  # provider boundary; response is intentionally sanitized
                logger.warning("Provider %s call failed: %s", identifier, type(exc).__name__)
                failures.append(ProviderFailure(provider=identifier, error_type=type(exc).__name__))

        successful.sort(key=lambda response: response.provider)
        failures.sort(key=lambda failure: failure.provider)
        limit = min(query.max_results, self._max_results)
        return CombinedSearchResponse(
            query=query.query,
            results=fuse_results(successful, self._reciprocal_rank_k, limit),
            selected_providers=[session.identifier for session in plan.providers],
            successful_providers=[
                ProviderExecution(
                    provider=response.provider,
                    latency_ms=response.latency_ms,
                    result_count=len(response.results),
                )
                for response in successful
            ],
            failed_providers=failures,
            timed_out_providers=sorted(timed_out),
            inferred_tags=sorted(plan.tags),
            estimated_cost_usd=plan.estimated_cost_usd,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    def _unavailable_response(
        self,
        query: SearchQuery,
        candidates: set[str],
        started: float,
    ) -> CombinedSearchResponse:
        timed_out, failures = self._classify_unavailable(candidates)
        return CombinedSearchResponse(
            query=query.query,
            selected_providers=[],
            failed_providers=failures,
            timed_out_providers=sorted(timed_out),
            inferred_tags=[],
            estimated_cost_usd=Decimal("0"),
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    def _classify_unavailable(
        self,
        candidates: set[str],
    ) -> tuple[set[str], list[ProviderFailure]]:
        recovering = self._registry.recovering_identifiers() & candidates
        health = self._registry.health()
        timed_out = set(recovering)
        failures: list[ProviderFailure] = []
        for identifier in sorted(candidates - recovering):
            state = health.get(identifier)
            if state is None or state.status != HealthStatus.UNHEALTHY:
                timed_out.add(identifier)
                continue
            error_type = state.message or "Unavailable"
            if error_type == "TimeoutError":
                timed_out.add(identifier)
                continue
            failures.append(ProviderFailure(provider=identifier, error_type=error_type))
        return timed_out, failures

    async def _call_provider(
        self, session: ProviderSession, query: SearchQuery, operation_id: int
    ) -> ProviderResponse:
        timeout_seconds = min(query.timeout_seconds, session.timeout_seconds)
        provider_task = asyncio.create_task(session.call_search(query, operation_id))
        try:
            done, pending = await asyncio.wait({provider_task}, timeout=timeout_seconds)
        except asyncio.CancelledError:
            # The MCP transport may finish its local await before downstream work
            # acknowledges cancellation, so the client generation is no longer safe
            # to route until it has been reset.
            session.record_timeout(operation_id)
            await self._cancel_and_drain(
                {provider_task},
                timeout_seconds=_CANCELLATION_GRACE_SECONDS,
            )
            raise
        if pending:
            session.record_timeout(operation_id)
            provider_task.cancel()
            self._track_cleanup(provider_task)
            raise TimeoutError
        try:
            return done.pop().result()
        except asyncio.CancelledError:
            # A client-generation reset can cancel this inner operation while
            # the caller remains active. Report that provider as timed out;
            # true caller cancellation is handled by the await above.
            session.record_timeout(operation_id)
            raise TimeoutError from None

    async def _cancel_and_drain(
        self,
        selected: set[asyncio.Task[ProviderResponse]],
        *,
        timeout_seconds: float,
    ) -> None:
        for task in selected:
            task.cancel()
        if not selected:
            return
        _, pending = await asyncio.wait(selected, timeout=timeout_seconds)
        for task in pending:
            self._track_cleanup(task)

    def _track_cleanup(self, task: asyncio.Task[Any]) -> None:
        self._cleanup_tasks.add(task)

        def finished(completed: asyncio.Task[Any]) -> None:
            self._cleanup_tasks.discard(completed)
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(finished)


def fuse_results(
    provider_responses: list[ProviderResponse], reciprocal_rank_k: int, limit: int
) -> list[SearchResult]:
    """Deduplicate and rank results with standard reciprocal-rank fusion."""

    fused: dict[str, SearchResult] = {}
    for response in sorted(provider_responses, key=lambda item: item.provider):
        provider_keys: set[str] = set()
        for sequential_rank, item in enumerate(response.results, start=1):
            rank = item.provider_rank or sequential_rank
            key = _canonical_key(item.url, item.title)
            if not key or key in provider_keys:
                continue
            provider_keys.add(key)
            source = ResultSource(
                provider=response.provider,
                rank=rank,
                original_score=item.original_score,
            )
            contribution = 1.0 / (reciprocal_rank_k + rank)
            existing = fused.get(key)
            if existing is None:
                fused[key] = SearchResult(
                    title=item.title,
                    url=item.url,
                    snippet=item.snippet,
                    raw_content=item.raw_content,
                    score=contribution,
                    sources=[source],
                    metadata=item.metadata,
                )
                continue
            existing.score += contribution
            existing.sources.append(source)
            existing.title = existing.title or item.title
            existing.url = existing.url or item.url
            existing.snippet = existing.snippet or item.snippet
            existing.raw_content = existing.raw_content or item.raw_content

    for result in fused.values():
        result.sources.sort(key=lambda source: (source.provider, source.rank))
    return sorted(
        fused.values(),
        key=lambda result: (
            -result.score,
            _canonical_key(result.url, result.title),
            result.title.casefold(),
        ),
    )[:limit]


def _canonical_key(url: str | None, title: str) -> str:
    if url:
        try:
            parsed = urlsplit(url.strip())
            hostname = (parsed.hostname or "").casefold()
            if hostname:
                port = parsed.port
                default_port = (parsed.scheme.casefold(), port) in {
                    ("http", 80),
                    ("https", 443),
                }
                netloc = hostname if port is None or default_port else f"{hostname}:{port}"
                query = urlencode(
                    sorted(
                        (key, value)
                        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                        if key.casefold() not in _TRACKING_QUERY_KEYS
                        and not key.casefold().startswith(_TRACKING_QUERY_PREFIXES)
                    ),
                    doseq=True,
                )
                path = parsed.path.rstrip("/") or "/"
                return "url:" + urlunsplit((parsed.scheme.casefold(), netloc, path, query, ""))
        except ValueError:
            pass
        return f"url:{url.strip().casefold()}"
    normalized_title = re.sub(r"\s+", " ", title).strip().casefold()
    return f"title:{normalized_title}" if normalized_title else ""


__all__ = ["SearchOrchestrator", "fuse_results"]
