"""Tests for the simple keyword router."""

from unittest.mock import AsyncMock

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.query_routing.simple_keyword_router import SimpleKeywordRouter


@pytest.fixture
def mock_providers():
    """Create mock providers."""
    providers = {}
    for name in ["linkup", "exa", "tavily", "perplexity", "firecrawl"]:
        provider = AsyncMock()
        providers[name] = provider
    return providers


@pytest.fixture
def router(mock_providers):
    """Create a simple keyword router instance."""
    return SimpleKeywordRouter(mock_providers)


class TestSimpleKeywordRouter:
    """Test the simple keyword router."""

    @pytest.mark.asyncio
    async def test_time_sensitive_queries(self, router):
        """Test routing of time-sensitive queries."""
        queries = [
            "news today",
            "latest updates",
            "breaking news",
            "what happened yesterday",
            "current events",
        ]

        for query_text in queries:
            query = SearchQuery(query=query_text)
            providers = await router.route(query)

            # Should prioritize linkup for time-sensitive queries
            assert "linkup" in providers
            assert providers[0] == "linkup"  # Should be first

    @pytest.mark.asyncio
    async def test_research_queries(self, router):
        """Test routing of research/academic queries."""
        queries = [
            "research paper on AI",
            "academic study climate change",
            "scientific journal quantum computing",
            "thesis about renewable energy",
        ]

        for query_text in queries:
            query = SearchQuery(query=query_text)
            providers = await router.route(query)

            # Should include exa for research queries
            assert "exa" in providers

    @pytest.mark.asyncio
    async def test_technical_queries(self, router):
        """Test routing of technical/programming queries."""
        queries = [
            "python documentation",
            "how to use FastAPI",
            "javascript tutorial",
            "https://github.com/user/repo",
        ]

        for query_text in queries:
            query = SearchQuery(query=query_text)
            providers = await router.route(query)

            # Should include appropriate providers
            if "github.com" in query_text:
                assert "firecrawl" in providers

    @pytest.mark.asyncio
    async def test_url_based_routing(self, router):
        """Test routing based on URLs in query."""
        test_cases = [
            ("https://github.com/user/repo", ["firecrawl", "exa"]),
            ("check https://arxiv.org/paper", ["exa", "perplexity"]),
            ("https://wikipedia.org/wiki/Python", ["tavily", "perplexity"]),
            ("https://twitter.com/user/status", ["linkup", "tavily"]),
        ]

        for query_text, expected_providers in test_cases:
            query = SearchQuery(query=query_text)
            providers = await router.route(query)

            for expected in expected_providers:
                assert expected in providers

    @pytest.mark.asyncio
    async def test_default_providers(self, router):
        """Test default providers for generic queries."""
        query = SearchQuery(query="random generic query without keywords")
        providers = await router.route(query)

        # Should return default providers
        assert len(providers) > 0
        assert "tavily" in providers
        assert "linkup" in providers
        assert "perplexity" in providers

    @pytest.mark.asyncio
    async def test_comprehensive_queries(self, router):
        """Test routing of comprehensive/detailed queries."""
        queries = [
            "comprehensive guide to machine learning",
            "detailed analysis of market trends",
            "complete overview of blockchain technology",
            "thorough comparison of cloud providers",
        ]

        for query_text in queries:
            query = SearchQuery(query=query_text)
            providers = await router.route(query)

            # Should include perplexity for comprehensive queries
            assert "perplexity" in providers

    @pytest.mark.asyncio
    async def test_provider_limit(self, router):
        """Test that router respects provider limits."""
        # Create a query that matches many keywords
        query = SearchQuery(
            query="latest news research paper comprehensive analysis website content"
        )
        providers = await router.route(query)

        # Should not exceed 5 providers
        assert len(providers) <= 5

    @pytest.mark.asyncio
    async def test_provider_availability(self, router):
        """Test router handles missing providers gracefully."""
        # Remove some providers
        limited_providers = {"linkup": router.providers["linkup"]}
        limited_router = SimpleKeywordRouter(limited_providers)

        query = SearchQuery(query="research paper")
        providers = await limited_router.route(query)

        # Should only return available providers
        assert len(providers) <= 1
        if providers:
            assert providers[0] == "linkup"

    @pytest.mark.asyncio
    async def test_score_based_ordering(self, router):
        """Test that providers are ordered by score."""
        # Query that strongly matches linkup keywords
        query = SearchQuery(query="latest breaking news today current updates")
        providers = await router.route(query)

        # Linkup should be first due to high score
        assert providers[0] == "linkup"

    @pytest.mark.asyncio
    async def test_empty_query(self, router):
        """Test handling of empty query."""
        query = SearchQuery(query="")
        providers = await router.route(query)

        # Should return default providers
        assert len(providers) > 0
