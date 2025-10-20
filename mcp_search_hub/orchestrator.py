"""Search orchestration built on top of FastMCP providers."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent

from .cache import SearchCache
from .metrics import MetricsTracker
from .models import CombinedSearchResponse, ProviderResult, SearchQuery, SearchResult
from .providers import ProviderRegistry, ProviderSession
from .routing import RoutingPlanner

logger = logging.getLogger(__name__)


class SearchOrchestrator:
    """Coordinates routing, provider execution, caching, and metrics."""

    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        planner: RoutingPlanner,
        cache: SearchCache,
        metrics: MetricsTracker,
        max_results: int,
    ) -> None:
        self._registry = registry
        self._planner = planner
        self._cache = cache
        self._metrics = metrics
        self._max_results = max(1, max_results)

    async def execute(self, query: SearchQuery) -> CombinedSearchResponse:
        """Execute a query across the configured providers."""

        cached = await self._cache.get(query)
        if cached:
            await self._metrics.record_success([], 0.0, cache_hit=True)
            return cached

        await self._registry.ensure_started()
        plan = self._planner.plan(query, self._registry.active_sessions())

        provider_results: list[ProviderResult] = []
        errors: list[tuple[str, Exception]] = []

        for session in plan.providers:
            try:
                call_result, latency_ms = await session.call_search(query)
                provider_results.append(
                    ProviderResult(
                        provider=session.identifier,
                        latency_ms=latency_ms,
                        results=self._parse_results(session, call_result),
                        cached=False,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - aggregated later
                logger.exception("Provider %s execution failed", session.identifier)
                errors.append((session.identifier, exc))

        if not provider_results:
            await self._metrics.record_failure([identifier for identifier, _ in errors])
            if errors:
                raise RuntimeError("All provider calls failed") from errors[0][1]
            raise RuntimeError("No provider results available")

        merged_results = self._merge(provider_results)
        response = CombinedSearchResponse(
            results=merged_results,
            providers=provider_results,
            metadata={
                "routing": {
                    "intent": plan.intent.value,
                    "tags": sorted(plan.tags),
                },
                "errors": [
                    {"provider": identifier, "message": str(exc)}
                    for identifier, exc in errors
                ],
            },
        )

        total_latency = sum(result.latency_ms for result in provider_results)
        await self._metrics.record_success(
            [result.provider for result in provider_results],
            total_latency,
            cache_hit=False,
        )
        await self._cache.set(query, response)
        return response

    def _parse_results(
        self, session: ProviderSession, call_result: Any
    ) -> list[SearchResult]:
        items = self._extract_items(call_result)
        results: list[SearchResult] = []
        for payload in items:
            normalised = self._normalise_item(session.identifier, payload)
            if normalised:
                results.append(normalised)
        return results[: self._max_results]

    def _extract_items(self, call_result: Any) -> list[Any]:
        if getattr(call_result, "data", None):
            data = call_result.data
            if isinstance(data, dict) and "results" in data:
                return list(data["results"])
            if isinstance(data, list):
                return list(data)
            if isinstance(data, dict):
                return [data]

        if getattr(call_result, "structured_content", None):
            structured = call_result.structured_content
            if isinstance(structured, dict) and "results" in structured:
                return list(structured["results"])
            if isinstance(structured, list):
                return list(structured)
            if isinstance(structured, dict):
                return [structured]

        content = getattr(call_result, "content", None)
        if not content:
            return []

        extracted: list[Any] = []
        for block in content:
            if isinstance(block, TextContent):
                try:
                    decoded = json.loads(block.text)
                except json.JSONDecodeError:
                    extracted.append({"snippet": block.text})
                else:
                    if isinstance(decoded, dict) and "results" in decoded:
                        extracted.extend(decoded["results"])
                    else:
                        extracted.append(decoded)
        return extracted

    def _normalise_item(self, provider: str, payload: Any) -> SearchResult | None:
        if isinstance(payload, SearchResult):
            return payload
        if isinstance(payload, str):
            return SearchResult(
                title=payload[:80],
                url=None,
                snippet=payload,
                score=0.0,
                provider=provider,
                raw_content=None,
                metadata={},
            )
        if not isinstance(payload, dict):
            return None

        metadata = dict(payload)
        title = metadata.pop("title", "") or metadata.pop("name", "")
        url = metadata.pop("url", metadata.pop("link", None))
        snippet = metadata.pop(
            "snippet", metadata.pop("description", metadata.pop("text", None))
        )
        score = metadata.pop(
            "score", metadata.pop("relevance", metadata.pop("confidence", 0.0))
        )
        raw_content = metadata.pop("raw_content", metadata.pop("content", None))

        try:
            score_value = float(score)
        except (TypeError, ValueError):
            score_value = 0.0

        return SearchResult(
            title=title,
            url=url,
            snippet=snippet,
            score=score_value,
            provider=provider,
            raw_content=raw_content,
            metadata=metadata,
        )

    def _merge(self, provider_results: list[ProviderResult]) -> list[SearchResult]:
        seen: dict[str, SearchResult] = {}
        merged: list[SearchResult] = []
        for provider_result in provider_results:
            for result in provider_result.results:
                key = (result.url or result.title or result.snippet or "").lower()
                if key and key in seen:
                    existing = seen[key]
                    sources = existing.metadata.setdefault("sources", [])
                    if isinstance(sources, list):
                        if result.provider not in sources:
                            sources.append(result.provider)
                    else:
                        existing.metadata["sources"] = [str(sources), result.provider]
                    existing.score = max(existing.score, result.score)
                else:
                    if key:
                        seen[key] = result
                    merged.append(result)
        merged.sort(key=lambda item: item.score, reverse=True)
        return merged[: self._max_results]


__all__ = ["SearchOrchestrator"]
