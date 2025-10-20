"""Provider selection logic."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..models import QueryIntent, SearchQuery
from ..providers import ProviderSession
from .classifier import QueryClassifier


@dataclass(frozen=True)
class RoutingPlan:
    """Represents the selected providers for a query."""

    providers: list[ProviderSession]
    tags: set[str]
    intent: QueryIntent


class RoutingPlanner:  # pylint: disable=too-few-public-methods
    """Select providers using classifier tags and provider weights."""

    def __init__(self, classifier: QueryClassifier, *, max_providers: int = 3):
        self._classifier = classifier
        self._max_providers = max(1, max_providers)

    def plan(
        self, query: SearchQuery, sessions: Iterable[ProviderSession]
    ) -> RoutingPlan:
        """Return a routing plan for the supplied query."""

        available = list(sessions)
        if not available:
            raise ValueError("No provider sessions available")

        tags = self._classifier.infer_tags(query)
        intent = self._classifier.classify_intent(query)

        scored: list[tuple[float, ProviderSession]] = []
        for session in available:
            overlap = len(tags & session.tags)
            base = session.weight
            if not session.tags:
                overlap += 1  # neutral providers always participate
            score = base * (1 + overlap)
            scored.append((score, session))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [session for _, session in scored[: self._max_providers]]
        if not selected:
            selected = [available[0]]
        return RoutingPlan(providers=selected, tags=tags, intent=intent)


__all__ = ["RoutingPlanner", "RoutingPlan"]
