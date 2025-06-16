"""Integration test for HybridRouter with SearchServer."""

from unittest.mock import AsyncMock

import pytest

from mcp_search_hub.config.settings import AppSettings
from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.models.results import SearchResponse, SearchResult
from mcp_search_hub.query_routing.hybrid_router import HybridRouter


@pytest.fixture
def mock_providers():
    """Create mock providers."""
    providers = {}
    for name in ["linkup", "exa", "tavily", "perplexity", "firecrawl"]:
        provider = AsyncMock()
        provider.search = AsyncMock(
            return_value=SearchResponse(
                results=[
                    SearchResult(
                        title=f"Result from {name}",
                        url=f"https://example.com/{name}",
                        snippet=f"Test result from {name}",
                        source=name,
                        score=0.9,
                    )
                ],
                query="test query",
                total_results=1,
                provider=name,
            )
        )
        providers[name] = provider
    return providers


@pytest.mark.asyncio
async def test_hybrid_router_full_flow(mock_providers):
    """Test the full flow of routing and execution."""
    settings = AppSettings()
    router = HybridRouter(mock_providers, settings)

    # Test simple query
    query = SearchQuery(query="latest news today")

    # Route the query
    decision = await router.route(query)
    assert decision.complexity_level == "simple"
    assert len(decision.providers) > 0
    assert "linkup" in decision.providers  # Should prioritize linkup for news

    # Execute the search
    results = await router.execute(query, decision)
    assert len(results) == len(decision.providers)

    # Verify results structure
    for provider_name, response in results.items():
        assert provider_name in decision.providers
        assert isinstance(response, SearchResponse)
        assert len(response.results) > 0
        assert response.provider == provider_name


@pytest.mark.asyncio
async def test_hybrid_router_complexity_tiers(mock_providers):
    """Test that different complexity queries route to appropriate tiers."""
    settings = AppSettings()
    router = HybridRouter(mock_providers, settings)

    test_cases = [
        ("weather today", "simple", 1),  # Tier 1
        ("how to build a REST API", "medium", 2),  # Tier 2
        (
            "analyze the environmental and economic impact of renewable energy",
            "complex",
            2,
        ),  # Tier 2 (LLM disabled)
    ]

    for query_text, expected_level, expected_tier in test_cases:
        query = SearchQuery(query=query_text)
        decision = await router.route(query)

        assert decision.complexity_level == expected_level
        assert len(decision.providers) > 0

        # Check metrics
        metrics = router.get_metrics()
        assert metrics[f"tier{expected_tier}_count"] > 0


@pytest.mark.asyncio
async def test_hybrid_router_error_handling(mock_providers):
    """Test error handling in routing and execution."""
    settings = AppSettings()
    router = HybridRouter(mock_providers, settings)

    # Make one provider fail
    mock_providers["linkup"].search.side_effect = Exception("Provider error")

    query = SearchQuery(query="test query")
    decision = await router.route(query)

    # Execute with provider failure
    results = await router.execute(query, decision)

    # Should still get results from other providers
    assert len(results) == len(decision.providers)

    # Failed provider should return empty response
    if "linkup" in results:
        assert len(results["linkup"].results) == 0


@pytest.mark.asyncio
async def test_hybrid_router_cascade_strategy(mock_providers):
    """Test cascade execution strategy."""
    settings = AppSettings()
    router = HybridRouter(mock_providers, settings)

    # Mock a complex query that uses cascade
    from mcp_search_hub.query_routing.hybrid_router import RoutingDecision

    decision = RoutingDecision(
        providers=["linkup", "tavily", "perplexity"],
        strategy="cascade",
        complexity_level="complex",
        confidence=0.85,
        explanation="Test cascade",
    )

    # Set up linkup to return enough results
    mock_providers["linkup"].search.return_value = SearchResponse(
        results=[
            SearchResult(
                title=f"Result {i}",
                url=f"https://example.com/{i}",
                snippet="Test",
                source="linkup",
                score=0.9,
            )
            for i in range(10)
        ],
        query="test query",
        total_results=10,
        provider="linkup",
    )

    query = SearchQuery(query="test query", max_results=5)
    results = await router.execute(query, decision)

    # Should only call the first provider since it has enough results
    assert "linkup" in results
    mock_providers["linkup"].search.assert_called_once()
    mock_providers["tavily"].search.assert_not_called()
    mock_providers["perplexity"].search.assert_not_called()
