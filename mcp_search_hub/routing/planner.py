"""Deterministic provider selection and budget enforcement."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import cast

from ..models import SearchQuery
from ..providers import ProviderSession
from .classifier import infer_tags


@dataclass(frozen=True, slots=True)
class RoutingPlan:
    """Selected providers and the cost decision that produced the selection."""

    providers: tuple[ProviderSession, ...]
    tags: frozenset[str]
    estimated_cost_usd: Decimal


class RoutingPlanner:
    """Own provider selection and request-budget enforcement."""

    def __init__(
        self,
        *,
        max_providers: int = 3,
        default_budget_usd: Decimal | None = None,
    ) -> None:
        self._max_providers = max(1, max_providers)
        self._default_budget_usd = default_budget_usd

    def plan(
        self,
        query: SearchQuery,
        sessions: Iterable[ProviderSession],
        *,
        configured_costs: Mapping[str, Decimal] | None = None,
    ) -> RoutingPlan:
        """Return one deterministic plan or raise for an impossible request."""

        available = {session.identifier: session for session in sessions}
        configured = (
            dict(configured_costs)
            if configured_costs is not None
            else {
                identifier: session.estimated_cost_usd for identifier, session in available.items()
            }
        )
        self.validate_request(query, configured)
        tags = infer_tags(query)
        budget = query.budget_usd if query.budget_usd is not None else self._default_budget_usd

        if query.providers is not None:
            selected = [available[name] for name in query.providers if name in available]
            if not selected:
                raise ValueError("No requested provider sessions are available")
            cost = _sum_costs(session.estimated_cost_usd for session in selected)
            if budget is not None and cost > budget:
                raise ValueError(f"Requested providers cost {cost} USD; budget is {budget} USD")
            return RoutingPlan(tuple(selected), frozenset(tags), cost)

        if not available:
            raise ValueError("No provider sessions are available")

        ranked = sorted(
            available.values(),
            key=lambda session: (
                -(session.weight * (1 + len(tags & session.tags))),
                session.identifier,
            ),
        )
        selected: list[ProviderSession] = []
        cost = Decimal("0")
        for session in ranked:
            next_cost = _sum_costs((cost, session.estimated_cost_usd))
            if budget is not None and next_cost > budget:
                continue
            selected.append(session)
            cost = next_cost
            if len(selected) == self._max_providers:
                break

        if not selected:
            raise ValueError("No provider fits the request budget")
        return RoutingPlan(tuple(selected), frozenset(tags), cost)

    def validate_request(
        self,
        query: SearchQuery,
        configured_costs: Mapping[str, Decimal],
    ) -> set[str]:
        """Validate the request and return providers eligible to satisfy recovery."""

        budget = query.budget_usd if query.budget_usd is not None else self._default_budget_usd
        if query.providers is None:
            if budget is None:
                return set(configured_costs)
            eligible = {
                identifier for identifier, cost in configured_costs.items() if cost <= budget
            }
            if configured_costs and not eligible:
                raise ValueError("No provider fits the request budget")
            return eligible
        unknown = sorted(set(query.providers) - set(configured_costs))
        if unknown:
            raise ValueError(f"Unknown requested providers: {unknown}")
        if len(query.providers) > self._max_providers:
            raise ValueError(
                f"Requested {len(query.providers)} providers; server limit is {self._max_providers}"
            )
        cost = _sum_costs(configured_costs[identifier] for identifier in query.providers)
        if budget is not None and cost > budget:
            raise ValueError(f"Requested providers cost {cost} USD; budget is {budget} USD")
        return set(query.providers)


def _sum_costs(costs: Iterable[Decimal]) -> Decimal:
    """Sum finite non-negative costs without Decimal context rounding."""

    values = tuple(costs)
    if not values:
        return Decimal("0")
    if any(not value.is_finite() or value < 0 for value in values):
        raise ValueError("Provider costs must be finite and non-negative")
    highest_place = max(value.adjusted() for value in values)
    lowest_place = min(cast(int, value.as_tuple().exponent) for value in values)
    carry_digits = len(str(len(values)))
    with localcontext() as context:
        context.prec = max(
            context.prec,
            highest_place - lowest_place + carry_digits + 1,
        )
        return sum(values, start=Decimal("0"))


__all__ = ["RoutingPlan", "RoutingPlanner"]
