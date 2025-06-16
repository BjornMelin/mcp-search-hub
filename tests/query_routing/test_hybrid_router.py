"""Tests for the hybrid router."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from mcp_search_hub.config.settings import AppSettings
from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.models.results import SearchResponse, SearchResult
from mcp_search_hub.query_routing.hybrid_router import HybridRouter, RoutingDecision


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


@pytest.fixture
def settings():
    """Create test settings."""
    return AppSettings(
        llm_routing_enabled=False,
        linkup_timeout=5000,
        exa_timeout=5000,
        tavily_timeout=5000,
        perplexity_timeout=5000,
        firecrawl_timeout=5000,
    )


@pytest.fixture
def router(mock_providers, settings):
    """Create a hybrid router instance."""
    return HybridRouter(mock_providers, settings)


class TestHybridRouter:
    """Test the hybrid router."""

    @pytest.mark.asyncio
    async def test_simple_query_routing(self, router):
        """Test routing of simple queries to Tier 1."""
        query = SearchQuery(query="weather today")
        decision = await router.route(query)

        assert decision.complexity_level == "simple"
        assert decision.confidence >= 0.9
        assert len(decision.providers) > 0
        assert decision.strategy == "parallel"
        assert "Simple query routed via keywords" in decision.explanation

        # Check metrics
        metrics = router.get_metrics()
        assert metrics["tier1_count"] == 1
        assert metrics["tier2_count"] == 0
        assert metrics["tier3_count"] == 0

    @pytest.mark.asyncio
    async def test_medium_query_routing(self, router):
        """Test routing of medium complexity queries to Tier 2."""
        query = SearchQuery(
            query="how to implement authentication in FastAPI with JWT tokens"
        )
        decision = await router.route(query)

        assert decision.complexity_level == "medium"
        assert decision.confidence >= 0.8
        assert len(decision.providers) > 0
        assert decision.strategy == "parallel"
        assert "Medium complexity routed via patterns" in decision.explanation

        # Check metrics
        metrics = router.get_metrics()
        assert metrics["tier2_count"] == 1

    @pytest.mark.asyncio
    async def test_complex_query_without_llm(self, router):
        """Test routing of complex queries falls back to Tier 2 when LLM disabled."""
        query = SearchQuery(
            query="analyze the environmental and economic impact of electric vehicles "
            "considering battery production, usage patterns, and end-of-life disposal"
        )
        decision = await router.route(query)

        # Should fall back to Tier 2 since LLM is disabled
        assert decision.complexity_level == "complex"
        assert decision.confidence == 0.7
        assert len(decision.providers) > 0
        assert decision.strategy == "parallel"
        assert "routed via patterns (LLM disabled)" in decision.explanation

    @pytest.mark.asyncio
    async def test_complex_query_with_llm(self, mock_providers):
        """Test routing of complex queries to Tier 3 when LLM enabled."""
        settings = AppSettings(llm_routing_enabled=True)
        router = HybridRouter(mock_providers, settings)

        # Mock the LLM router's score_provider method
        from unittest.mock import Mock

        with patch.object(router.tier3_router, "score_provider") as mock_score_provider:
            # Create a mock score object with weighted_score attribute
            mock_score = Mock()
            mock_score.weighted_score = 0.9

            # Make the mock return a coroutine
            async def mock_async_score(*args, **kwargs):
                return mock_score

            mock_score_provider.side_effect = mock_async_score

            query = SearchQuery(
                query="analyze and compare the environmental, economic, and social impacts of renewable energy considering various factors"
            )
            decision = await router.route(query)

            assert decision.complexity_level == "complex"
            assert decision.confidence == 0.85
            assert "Complex query routed via LLM" in decision.explanation

    @pytest.mark.asyncio
    async def test_parallel_execution(self, router):
        """Test parallel execution of searches."""
        query = SearchQuery(query="test query")
        decision = RoutingDecision(
            providers=["linkup", "tavily", "perplexity"],
            strategy="parallel",
            complexity_level="simple",
            confidence=0.9,
            explanation="Test",
        )

        results = await router.execute(query, decision)

        assert len(results) == 3
        assert all(provider in results for provider in decision.providers)
        # All providers should have been called
        for provider in decision.providers:
            router.providers[provider].search.assert_called_once_with(query)

    @pytest.mark.asyncio
    async def test_cascade_execution(self, router):
        """Test cascade execution with early stopping."""
        query = SearchQuery(query="test query", max_results=2)
        decision = RoutingDecision(
            providers=["linkup", "tavily", "perplexity"],
            strategy="cascade",
            complexity_level="complex",
            confidence=0.85,
            explanation="Test cascade",
        )

        # Make the first provider return 2 results
        router.providers["linkup"].search.return_value = SearchResponse(
            results=[
                SearchResult(
                    title=f"Result {i}",
                    url=f"https://example.com/{i}",
                    snippet="Test",
                    source="linkup",
                    score=0.9,
                )
                for i in range(2)
            ],
            query="test query",
            total_results=2,
            provider="linkup",
        )

        results = await router.execute(query, decision)

        # Should only call the first provider since it returns enough results
        assert len(results) == 1
        assert "linkup" in results
        router.providers["linkup"].search.assert_called_once()
        router.providers["tavily"].search.assert_not_called()
        router.providers["perplexity"].search.assert_not_called()

    @pytest.mark.asyncio
    async def test_provider_timeout_handling(self, router):
        """Test handling of provider timeouts."""
        query = SearchQuery(query="test query")

        # Make one provider timeout
        async def timeout_search(*args, **kwargs):
            await asyncio.sleep(10)  # Longer than timeout

        router.providers["linkup"].search = timeout_search

        results = await router._execute_parallel(query, ["linkup", "tavily"])

        # Should get results from both, but linkup will have empty results
        assert len(results) == 2
        assert "tavily" in results
        assert "linkup" in results
        assert len(results["linkup"].results) == 0  # Empty due to timeout
        assert len(results["tavily"].results) > 0

    @pytest.mark.asyncio
    async def test_provider_error_handling(self, router):
        """Test handling of provider errors."""
        query = SearchQuery(query="test query")

        # Make one provider raise an exception
        router.providers["linkup"].search.side_effect = Exception("Test error")

        results = await router._execute_parallel(query, ["linkup", "tavily"])

        # Should get results from both, but linkup will have empty results
        assert len(results) == 2
        assert "tavily" in results
        assert "linkup" in results
        assert len(results["linkup"].results) == 0  # Empty due to error
        assert len(results["tavily"].results) > 0

    @pytest.mark.asyncio
    async def test_metrics_tracking(self, router):
        """Test metrics are properly tracked."""
        queries = [
            SearchQuery(query="news today"),  # Simple (0.0)
            SearchQuery(query="how to build a REST API"),  # Medium (0.3)
            SearchQuery(
                query="analyze the environmental and economic impact of renewable energy"
            ),  # Complex (>0.7)
        ]

        for query in queries:
            await router.route(query)

        metrics = router.get_metrics()
        assert metrics["total_queries"] == 3
        assert metrics["tier1_count"] == 1  # news today
        assert metrics["tier2_count"] == 2  # how to build + complex fallback
        assert metrics["tier3_count"] == 0  # LLM disabled
        assert metrics["avg_routing_time_ms"] > 0

        # Check percentages
        assert metrics["tier1_percentage"] == (1 / 3) * 100
        assert metrics["tier2_percentage"] == (2 / 3) * 100
        assert metrics["tier3_percentage"] == 0

    @pytest.mark.asyncio
    async def test_empty_provider_list(self, router):
        """Test handling when no providers are selected."""
        # Mock tier1 router to return empty list
        router.tier1_router.route = AsyncMock(return_value=[])

        query = SearchQuery(query="obscure query")
        decision = await router.route(query)

        assert len(decision.providers) == 0
        assert decision.complexity_level == "simple"
