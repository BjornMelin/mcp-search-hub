"""Tests for the pattern router."""

from unittest.mock import AsyncMock, patch

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.query_routing.pattern_router import PatternRouter


@pytest.fixture
def mock_providers():
    """Create mock providers."""
    providers = {}
    for name in ["linkup", "exa", "tavily", "perplexity", "firecrawl"]:
        provider = AsyncMock()
        provider.name = name
        providers[name] = provider
    return providers


@pytest.fixture
def router(mock_providers):
    """Create a pattern router instance."""
    return PatternRouter(mock_providers)


class TestPatternRouter:
    """Test the pattern router."""

    @pytest.mark.asyncio
    async def test_technical_content_routing(self, router):
        """Test routing of technical content queries."""
        queries = [
            "how to implement OAuth in FastAPI",
            "python async programming tutorial",
            "debugging JavaScript memory leaks",
            "docker compose configuration guide",
        ]

        for query_text in queries:
            query = SearchQuery(query=query_text)
            providers = await router.route(query)

            # Should include technical providers
            assert len(providers) > 0
            assert any(p in providers for p in ["perplexity", "firecrawl"])

    @pytest.mark.asyncio
    async def test_academic_content_routing(self, router):
        """Test routing of academic content queries."""
        queries = [
            "machine learning research papers 2024",
            "quantum computing recent advances",
            "climate change scientific studies",
            "neuroscience peer-reviewed articles",
        ]

        for query_text in queries:
            query = SearchQuery(query=query_text)
            providers = await router.route(query)

            # Should include providers suitable for academic content
            assert len(providers) >= 2
            # At least one of these academic-friendly providers should be included
            assert any(p in providers for p in ["exa", "perplexity", "tavily"])

    @pytest.mark.asyncio
    async def test_news_content_routing(self, router):
        """Test routing of news content queries."""
        queries = [
            "tech industry news updates",
            "stock market analysis today",
            "political developments this week",
            "sports championship results",
        ]

        for query_text in queries:
            query = SearchQuery(query=query_text)
            providers = await router.route(query)

            # Should include providers suitable for news content
            assert len(providers) >= 2
            # At least one of these news-friendly providers should be included
            assert any(p in providers for p in ["linkup", "tavily", "perplexity"])

    @pytest.mark.asyncio
    async def test_tutorial_content_routing(self, router):
        """Test routing of tutorial/guide queries."""
        queries = [
            "step by step React tutorial",
            "beginner's guide to machine learning",
            "how to set up kubernetes cluster",
            "complete guide to web scraping",
        ]

        for query_text in queries:
            query = SearchQuery(query=query_text)
            providers = await router.route(query)

            # Should include comprehensive providers
            assert "perplexity" in providers
            assert len(providers) >= 2

    @pytest.mark.asyncio
    async def test_commercial_content_routing(self, router):
        """Test routing of commercial/shopping queries."""
        queries = [
            "best laptop deals 2024",
            "product reviews smartphones",
            "compare prices online shopping",
            "discount codes electronics",
        ]

        for query_text in queries:
            query = SearchQuery(query=query_text)
            providers = await router.route(query)

            # Should include general search providers
            assert len(providers) > 0
            assert any(p in providers for p in ["tavily", "perplexity"])

    @pytest.mark.asyncio
    async def test_provider_scoring(self, router):
        """Test provider scoring mechanism."""
        # Mock the content detector
        with patch.object(
            router.content_detector, "detect_content_type"
        ) as mock_detect:
            mock_detect.return_value = "technical"

            features = {"query": "test query"}
            score_result = await router.score_provider(
                "perplexity", router.providers["perplexity"], features
            )

            # Perplexity should score high for technical content
            assert score_result.total_score > 0.7

            # Linkup should score lower for technical content
            score_result = await router.score_provider(
                "linkup", router.providers["linkup"], features
            )
            assert score_result.total_score < 0.7

    @pytest.mark.asyncio
    async def test_fallback_routing(self, router):
        """Test fallback routing for unclassified queries."""
        # Query with no clear content type
        query = SearchQuery(query="xyz abc 123")
        providers = await router.route(query)

        # Should still return providers
        assert len(providers) > 0
        # Should include general providers
        assert any(p in providers for p in ["tavily", "perplexity"])

    @pytest.mark.asyncio
    async def test_provider_limit(self, router):
        """Test that router respects provider limits."""
        # Query that matches multiple patterns
        query = SearchQuery(
            query="latest research tutorial comprehensive guide news analysis"
        )
        providers = await router.route(query)

        # Should not exceed 5 providers
        assert len(providers) <= 5
        # Should be ordered by score
        assert len(providers) >= 3

    @pytest.mark.asyncio
    async def test_quality_thresholds(self, router):
        """Test quality score thresholds."""
        # Create a router with limited providers
        limited_providers = {
            "linkup": router.providers["linkup"],
            "tavily": router.providers["tavily"],
        }
        limited_router = PatternRouter(limited_providers)

        # Technical query should still work with limited providers
        query = SearchQuery(query="python programming tutorial")
        providers = await limited_router.route(query)

        # Should return available providers even if not ideal
        assert len(providers) > 0
        assert all(p in limited_providers for p in providers)

    @pytest.mark.asyncio
    async def test_empty_provider_handling(self, router):
        """Test handling when no providers match well."""
        # Create router with no providers
        empty_router = PatternRouter({})

        query = SearchQuery(query="test query")
        providers = await empty_router.route(query)

        # Should return empty list gracefully
        assert providers == []

    @pytest.mark.asyncio
    async def test_cross_domain_queries(self, router):
        """Test routing of cross-domain queries."""
        query = SearchQuery(
            query="machine learning applications in financial news analysis"
        )
        providers = await router.route(query)

        # Should include providers from multiple domains
        assert len(providers) >= 3
        # Should include both technical and news providers
        assert any(p in providers for p in ["exa", "perplexity"])  # technical/academic
        assert any(p in providers for p in ["linkup", "tavily"])  # news

    @pytest.mark.asyncio
    async def test_question_queries(self, router):
        """Test routing of question-based queries."""
        queries = [
            "what is quantum computing?",
            "how does blockchain work?",
            "why is climate change happening?",
            "when was Python created?",
        ]

        for query_text in queries:
            query = SearchQuery(query=query_text)
            providers = await router.route(query)

            # Questions should get comprehensive providers
            assert len(providers) >= 2
            assert "tavily" in providers  # Good for factual questions
