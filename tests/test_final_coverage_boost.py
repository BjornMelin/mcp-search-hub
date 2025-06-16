"""Final targeted tests to boost coverage for specific missing lines."""

from unittest.mock import AsyncMock

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.query_routing.complexity_classifier import ComplexityClassifier
from mcp_search_hub.query_routing.hybrid_router import HybridRouter


class TestFinalCoverageBoost:
    """Tests targeting specific missing lines for coverage."""

    def test_complexity_classifier_empty_query_edge_case(self):
        """Test complexity classifier with empty query to hit missing line 128."""
        classifier = ComplexityClassifier()

        # Test with empty query
        query = SearchQuery(query="")
        result = classifier.classify(query)

        # Should still return simple complexity
        assert result.level == "simple"
        assert result.score < 0.3

    @pytest.mark.asyncio
    async def test_hybrid_router_exception_handling(self):
        """Test exception handling in hybrid router search methods."""
        # Create mock providers
        providers = {"test_provider": AsyncMock()}

        # Make the provider raise an exception
        providers["test_provider"].search.side_effect = Exception("Test exception")

        from mcp_search_hub.config.settings import AppSettings

        settings = AppSettings(llm_routing_enabled=False)
        router = HybridRouter(providers, settings)

        query = SearchQuery(query="test query")

        # Test exception handling in _search_with_provider method
        result = await router._search_with_provider(
            "test_provider", providers["test_provider"], query
        )

        # Should return empty response on exception
        assert len(result.results) == 0
        assert result.provider == "test_provider"

    @pytest.mark.asyncio
    async def test_hybrid_router_cascade_break_condition(self):
        """Test cascade execution early break condition."""
        # Create mock providers
        providers = {
            "provider1": AsyncMock(),
            "provider2": AsyncMock(),
            "provider3": AsyncMock(),
        }

        # Configure first provider to return enough results
        from mcp_search_hub.models.results import SearchResponse, SearchResult

        providers["provider1"].search.return_value = SearchResponse(
            results=[
                SearchResult(
                    title=f"Result {i}",
                    url=f"https://example.com/{i}",
                    snippet="Test result",
                    source="provider1",
                    score=0.9,
                )
                for i in range(5)  # Return 5 results
            ],
            query="test query",
            total_results=5,
            provider="provider1",
        )

        from mcp_search_hub.config.settings import AppSettings

        settings = AppSettings(llm_routing_enabled=False)
        router = HybridRouter(providers, settings)

        query = SearchQuery(query="test query", max_results=3)  # Only want 3 results

        # Test cascade execution with early break
        results = await router._execute_cascade(
            query, ["provider1", "provider2", "provider3"]
        )

        # Should only call provider1 and break early since it provided enough results
        assert "provider1" in results
        providers["provider1"].search.assert_called_once()
        # provider2 and provider3 should not be called due to early break
        providers["provider2"].search.assert_not_called()
        providers["provider3"].search.assert_not_called()
