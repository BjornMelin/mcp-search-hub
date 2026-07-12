"""Routing and budget contract tests."""

from decimal import Decimal

import pytest

from mcp_search_hub.models import SearchQuery
from mcp_search_hub.routing import RoutingPlanner, infer_tags
from tests.conftest import StubProviderSession


def test_infer_tags_combines_explicit_and_keywords() -> None:
    query = SearchQuery(query="Latest Python CVE research", tags={"custom"})
    assert infer_tags(query) == {"code", "custom", "news", "research", "security"}
    assert infer_tags(SearchQuery(query="weather tomorrow")) == {"general"}


def test_automatic_routing_is_weighted_deterministic_and_budgeted() -> None:
    planner = RoutingPlanner(max_providers=2, default_budget_usd=Decimal("0.03"))
    sessions = [
        StubProviderSession("zeta", tags={"code"}, weight=2, cost="0.02"),
        StubProviderSession("alpha", tags={"code"}, weight=2, cost="0.02"),
        StubProviderSession("general", tags={"general"}, cost="0.01"),
    ]
    plan = planner.plan(SearchQuery(query="Python function"), sessions)
    assert [provider.identifier for provider in plan.providers] == ["alpha", "general"]
    assert plan.estimated_cost_usd == Decimal("0.03")


def test_explicit_provider_list_wins() -> None:
    planner = RoutingPlanner(max_providers=2)
    sessions = [
        StubProviderSession("alpha", tags={"code"}, cost="0.01"),
        StubProviderSession("beta", tags={"news"}, cost="0.02"),
    ]
    query = SearchQuery(
        query="Python news",
        providers=["beta"],
        budget_usd=Decimal("0.02"),
    )
    assert [item.identifier for item in planner.plan(query, sessions).providers] == ["beta"]


@pytest.mark.parametrize(
    ("query", "message"),
    [
        (SearchQuery(query="x", providers=["missing"]), "Unknown requested"),
        (
            SearchQuery(query="x", providers=["alpha", "beta"]),
            "server limit",
        ),
        (
            SearchQuery(query="x", providers=["alpha"], budget_usd=Decimal("0.01")),
            "budget is",
        ),
    ],
)
def test_explicit_provider_errors(query: SearchQuery, message: str) -> None:
    planner = RoutingPlanner(max_providers=1)
    sessions = [
        StubProviderSession("alpha", cost="0.02"),
        StubProviderSession("beta"),
    ]
    with pytest.raises(ValueError, match=message):
        planner.plan(query, sessions)


def test_planner_rejects_empty_or_unaffordable_pool() -> None:
    planner = RoutingPlanner(max_providers=1, default_budget_usd=Decimal("0.01"))
    with pytest.raises(ValueError, match="No provider sessions"):
        planner.plan(SearchQuery(query="x"), [])
    with pytest.raises(ValueError, match="fits the request budget"):
        planner.plan(
            SearchQuery(query="x"),
            [StubProviderSession("alpha", cost="0.02")],
        )
