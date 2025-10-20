"""Routing planner and classifier tests."""

from __future__ import annotations

from mcp_search_hub.models import SearchQuery
from mcp_search_hub.routing import QueryClassifier, RoutingPlanner

from tests.conftest import StubProviderSession


def test_classifier_tags():
    classifier = QueryClassifier()
    query = SearchQuery(query="Latest security exploit news", max_results=5)
    tags = classifier.infer_tags(query)
    assert "security" in tags
    assert classifier.classify_intent(query).value in tags


def test_planner_selects_matching_provider():
    classifier = QueryClassifier()
    planner = RoutingPlanner(classifier, max_providers=1)
    sessions = [
        StubProviderSession("alpha", tags={"general"}, responses=[]),
        StubProviderSession("beta", tags={"code"}, responses=[]),
    ]
    query = SearchQuery(query="Write python function", max_results=5)
    plan = planner.plan(query, sessions)
    assert plan.providers[0].identifier == "beta"
    assert "code" in plan.tags
