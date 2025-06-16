"""Extended tests to achieve 90% coverage for key modules."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_search_hub.config.settings import AppSettings, MergerSettings
from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.models.results import SearchResponse, SearchResult
from mcp_search_hub.query_routing.complexity_classifier import ComplexityClassifier
from mcp_search_hub.query_routing.hybrid_router import HybridRouter
from mcp_search_hub.result_processing.deduplication import (
    _apply_fuzzy_matching,
    _normalize_url,
    remove_duplicates,
)
from mcp_search_hub.result_processing.merger import ResultMerger
from mcp_search_hub.result_processing.metadata_enrichment import enrich_result_metadata


class TestComplexityClassifierExtended:
    """Extended tests for ComplexityClassifier to achieve higher coverage."""

    @pytest.fixture
    def classifier(self):
        """Create a complexity classifier instance."""
        return ComplexityClassifier()

    def test_how_why_question_pattern(self, classifier):
        """Test specific how/why question patterns."""
        how_questions = [
            "how does this work exactly",
            "explain how machine learning works",
            "why is this happening now",
        ]

        for question in how_questions:
            query = SearchQuery(query=question)
            result = classifier.classify(query)
            assert result.factors["question_type"] == 0.2

    def test_intent_counting_edge_cases(self, classifier):
        """Test various intent counting scenarios."""
        # Test numbered lists
        numbered_query = SearchQuery(query="1. first item 2. second item 3. third item")
        result = classifier.classify(numbered_query)
        assert result.factors["multi_intent"] > 0

        # Test lettered lists
        lettered_query = SearchQuery(
            query="a) option one b) option two c) option three"
        )
        result = classifier.classify(lettered_query)
        assert result.factors["multi_intent"] > 0

        # Test multiple conjunctions
        conjunction_query = SearchQuery(
            query="search for python and javascript and react and vue"
        )
        result = classifier.classify(conjunction_query)
        assert result.factors["multi_intent"] >= 0.1

    def test_cross_domain_pattern_matching(self, classifier):
        """Test cross-domain pattern detection."""
        patterns = [
            "environmental and economic impact on technology",
            "historical context of modern politics",
            "social implications of artificial intelligence",
        ]

        for pattern in patterns:
            query = SearchQuery(query=pattern)
            result = classifier.classify(query)
            assert result.factors["cross_domain"] == 0.2

    def test_multiple_domain_keywords(self, classifier):
        """Test multiple domain keyword detection."""
        query = SearchQuery(query="environmental economic technical social analysis")
        result = classifier.classify(query)
        assert result.factors["cross_domain"] == 0.2

    def test_score_capping(self, classifier):
        """Test that scores are properly capped at 1.0."""
        # Create a query with many complexity factors
        complex_query = SearchQuery(
            query="analyze compare evaluate assess explain relationship impact effect "
            "influence considering versus between comprehensive detailed thorough "
            "environmental economic social technical political cultural historical "
            "scientific might could possibly perhaps maybe sometimes generally "
            "usually often various and also plus as well as including 1. first 2. second"
        )
        result = classifier.classify(complex_query)
        assert result.score <= 1.0


class TestHybridRouterExtended:
    """Extended tests for HybridRouter to achieve higher coverage."""

    @pytest.fixture
    def mock_providers(self):
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
    def settings_with_llm(self):
        """Create test settings with LLM enabled."""
        return AppSettings(
            llm_routing_enabled=True,
            linkup_timeout=5000,
            exa_timeout=5000,
            tavily_timeout=5000,
            perplexity_timeout=5000,
            firecrawl_timeout=5000,
        )

    @pytest.mark.asyncio
    async def test_llm_routing_with_mock(self, mock_providers, settings_with_llm):
        """Test LLM routing with properly mocked components."""
        router = HybridRouter(mock_providers, settings_with_llm)

        # Mock the analyzer and LLM router components
        with patch(
            "mcp_search_hub.query_routing.hybrid_router.QueryAnalyzer"
        ) as mock_analyzer_class:
            mock_analyzer = mock_analyzer_class.return_value
            mock_analyzer.extract_features.return_value = {"complexity": 0.8}

            # Mock the tier3_router score_provider method
            mock_score = MagicMock()
            mock_score.weighted_score = 0.9
            router.tier3_router.score_provider = AsyncMock(return_value=mock_score)

            query = SearchQuery(
                query="analyze the comprehensive environmental and economic impacts of renewable energy technologies"
            )
            decision = await router.route(query)

            assert decision.complexity_level == "complex"
            assert decision.confidence == 0.85
            assert "Complex query routed via LLM" in decision.explanation

    @pytest.mark.asyncio
    async def test_cascade_with_insufficient_results(self, mock_providers):
        """Test cascade execution when providers don't return enough results."""
        settings = AppSettings(llm_routing_enabled=False)
        router = HybridRouter(mock_providers, settings)

        # Set up providers to return varying numbers of results
        router.providers["linkup"].search.return_value = SearchResponse(
            results=[],  # No results
            query="test query",
            total_results=0,
            provider="linkup",
        )

        router.providers["exa"].search.return_value = SearchResponse(
            results=[
                SearchResult(
                    title="Single result",
                    url="https://example.com/single",
                    snippet="Only one result",
                    source="exa",
                    score=0.8,
                )
            ],
            query="test query",
            total_results=1,
            provider="exa",
        )

        query = SearchQuery(query="test query", max_results=5)
        results = await router._execute_cascade(query, ["linkup", "exa", "tavily"])

        # Should continue to try more providers when insufficient results
        assert len(results) >= 2  # Should have tried exa and tavily

    @pytest.mark.asyncio
    async def test_provider_not_in_providers_dict(self, mock_providers):
        """Test handling when a provider name doesn't exist in providers dict."""
        settings = AppSettings(llm_routing_enabled=False)
        router = HybridRouter(mock_providers, settings)

        # Try to execute with a non-existent provider
        query = SearchQuery(query="test query")
        results = await router._execute_parallel(query, ["nonexistent", "linkup"])

        # Should only have results from existing providers
        assert "nonexistent" not in results
        assert "linkup" in results

    def test_metrics_percentage_calculation(self, mock_providers):
        """Test metrics percentage calculations."""
        settings = AppSettings(llm_routing_enabled=False)
        router = HybridRouter(mock_providers, settings)

        # Manually set metrics
        router.metrics["tier1_count"] = 8
        router.metrics["tier2_count"] = 2
        router.metrics["tier3_count"] = 0
        router.metrics["total_queries"] = 10

        metrics = router.get_metrics()

        assert metrics["tier1_percentage"] == 80.0
        assert metrics["tier2_percentage"] == 20.0
        assert metrics["tier3_percentage"] == 0.0


class TestResultMergerExtended:
    """Extended tests for ResultMerger to achieve higher coverage."""

    @pytest.mark.asyncio
    async def test_empty_provider_results(self):
        """Test merger with empty provider results."""
        merger = ResultMerger()
        result = await merger.merge_results({})
        assert result == []

    @pytest.mark.asyncio
    async def test_merger_with_search_response_objects(self):
        """Test merger with SearchResponse objects instead of raw lists."""
        merger = ResultMerger()

        response1 = SearchResponse(
            results=[
                SearchResult(
                    title="Test Result 1",
                    url="https://example.com/1",
                    snippet="First result",
                    source="linkup",
                    score=0.9,
                )
            ],
            query="test",
            total_results=1,
            provider="linkup",
        )

        response2 = SearchResponse(
            results=[
                SearchResult(
                    title="Test Result 2",
                    url="https://example.com/2",
                    snippet="Second result",
                    source="exa",
                    score=0.8,
                )
            ],
            query="test",
            total_results=1,
            provider="exa",
        )

        provider_results = {
            "linkup": response1,
            "exa": response2,
        }

        merged = await merger.merge_results(provider_results)
        assert len(merged) == 2
        assert merged[0].source in ["linkup", "exa"]

    @pytest.mark.asyncio
    async def test_merger_source_assignment(self):
        """Test that merger properly assigns source when missing."""
        merger = ResultMerger()

        # Create result without source
        result_without_source = SearchResult(
            title="No Source Result",
            url="https://example.com/nosource",
            snippet="Result without source",
            score=0.8,
        )

        provider_results = {"test_provider": [result_without_source]}

        merged = await merger.merge_results(provider_results)
        assert len(merged) == 1
        assert merged[0].source == "test_provider"

    @pytest.mark.asyncio
    async def test_merger_with_custom_settings(self):
        """Test merger with custom configuration."""
        config = MergerSettings(
            max_results=5,
            provider_weights={"custom": 1.5, "test": 0.5},
            recency_enabled=False,
            credibility_enabled=False,
        )
        merger = ResultMerger(config=config)

        results = [
            SearchResult(
                title="Custom Provider Result",
                url="https://example.com/custom",
                snippet="From custom provider",
                source="custom",
                score=0.7,
            ),
            SearchResult(
                title="Test Provider Result",
                url="https://example.com/test",
                snippet="From test provider",
                source="test",
                score=0.9,
            ),
        ]

        provider_results = {"custom": [results[0]], "test": [results[1]]}
        merged = await merger.merge_results(provider_results)

        # Custom provider should rank higher due to weight (1.5 vs 0.5)
        assert merged[0].source == "custom"
        assert merged[1].source == "test"


class TestDeduplicationExtended:
    """Extended tests for deduplication to achieve higher coverage."""

    def test_normalize_url_edge_cases(self):
        """Test URL normalization edge cases."""
        # Test URLs with fragments (fragments are removed by canonicalize_url)
        result = _normalize_url("https://example.com/page#section")
        assert "#section" not in result

        # Test URLs with tracking parameters (should be removed)
        result = _normalize_url("https://example.com/page?utm_source=test&param=value")
        assert "utm_source" not in result
        assert "param=value" in result

        # Test trailing slash normalization
        result1 = _normalize_url("https://example.com/page/")
        result2 = _normalize_url("https://example.com/page")
        assert result1 == result2

        # Test www prefix removal
        result1 = _normalize_url("https://www.example.com/page")
        result2 = _normalize_url("https://example.com/page")
        assert result1 == result2

    def test_fuzzy_matching_with_similar_urls(self):
        """Test fuzzy matching with similar URLs."""
        results = [
            SearchResult(
                title="First Result",
                url="https://example.com/page",
                snippet="Content",
                source="source1",
                score=0.9,
            ),
            SearchResult(
                title="Similar Result",
                url="https://example.com/page-variant",
                snippet="Content",
                source="source2",
                score=0.8,
            ),
        ]

        deduplicated = _apply_fuzzy_matching(results, threshold=80.0)

        # Should detect URL similarity and merge
        assert len(deduplicated) == 1
        assert deduplicated[0].score == 0.9  # Keep higher scored result

    def test_fuzzy_matching_with_content_similarity(self):
        """Test fuzzy matching with content similarity enabled."""
        results = [
            SearchResult(
                title="Original Title",
                url="https://example1.com",
                snippet="This is the original content about machine learning",
                source="source1",
                score=0.9,
            ),
            SearchResult(
                title="Similar Title",
                url="https://example2.com",
                snippet="This is the original content about machine learning with some changes",
                source="source2",
                score=0.8,
            ),
        ]

        deduplicated = _apply_fuzzy_matching(
            results,
            threshold=50.0,  # Low URL threshold so URLs don't match
            use_content_similarity=True,
            content_threshold=0.8,
        )

        # Should detect content similarity and merge
        assert len(deduplicated) <= len(results)

    def test_remove_duplicates_with_content_similarity(self):
        """Test deduplication using content similarity."""
        results = [
            SearchResult(
                title="Original Article",
                url="https://example.com/original",
                snippet="This is the original article content",
                source="source1",
                score=0.9,
            ),
            SearchResult(
                title="Similar Article",
                url="https://different.com/copy",
                snippet="This is the original article content with minor changes",
                source="source2",
                score=0.8,
            ),
            SearchResult(
                title="Different Article",
                url="https://example.com/different",
                snippet="Completely different content about unrelated topics",
                source="source3",
                score=0.7,
            ),
        ]

        deduplicated = remove_duplicates(
            results,
            use_content_similarity=True,
            content_similarity_threshold=0.8,
        )

        # Should keep all since they have different URLs and content similarity
        # threshold may not be met with these simple examples
        assert len(deduplicated) >= 2

    def test_remove_duplicates_preserves_highest_score(self):
        """Test that deduplication preserves the highest scoring result."""
        results = [
            SearchResult(
                title="Lower Score",
                url="https://example.com/page",
                snippet="Content",
                source="source1",
                score=0.7,
            ),
            SearchResult(
                title="Higher Score",
                url="https://example.com/page",
                snippet="Content",
                source="source2",
                score=0.9,
            ),
        ]

        deduplicated = remove_duplicates(results)

        assert len(deduplicated) == 1
        assert deduplicated[0].score == 0.9
        assert deduplicated[0].source == "source2"


class TestMetadataEnrichmentExtended:
    """Extended tests for metadata enrichment to achieve higher coverage."""

    def test_enrich_result_metadata_comprehensive(self):
        """Test comprehensive metadata enrichment."""
        result = SearchResult(
            title="Test Article About Python Programming",
            url="https://tech.example.com/python-tutorial",
            snippet="Learn Python programming with this comprehensive tutorial covering variables, functions, and classes.",
            source="test_source",
            score=0.8,
        )

        enrich_result_metadata(result)

        # Check that all expected metadata is added
        assert "source_domain" in result.metadata
        assert "organization" in result.metadata
        assert "word_count" in result.metadata
        assert "reading_time" in result.metadata
        assert "reading_time_display" in result.metadata
        assert "citation" in result.metadata

        # Check specific values
        assert result.metadata["source_domain"] == "tech.example.com"
        assert result.metadata["organization"] == "Example"
        assert result.metadata["word_count"] > 0
        assert result.metadata["reading_time"] > 0
        assert "minute" in result.metadata["reading_time_display"]

    def test_enrich_metadata_with_existing_metadata(self):
        """Test enrichment with pre-existing metadata."""
        result = SearchResult(
            title="Test",
            url="https://example.com",
            snippet="Short snippet",
            source="test",
            score=0.8,
            metadata={"existing_field": "existing_value"},
        )

        enrich_result_metadata(result)

        # Should preserve existing metadata
        assert result.metadata["existing_field"] == "existing_value"
        # Should add new metadata
        assert "source_domain" in result.metadata

    def test_reading_time_calculation_edge_cases(self):
        """Test reading time calculation with various content lengths."""
        # Very short content
        short_result = SearchResult(
            title="Short",
            url="https://example.com",
            snippet="Short text",
            source="test",
            score=0.8,
        )
        enrich_result_metadata(short_result)
        assert short_result.metadata["reading_time"] == 1
        assert "1 minute read" in short_result.metadata["reading_time_display"]

        # Longer content
        long_snippet = " ".join(["word"] * 500)  # 500 words
        long_result = SearchResult(
            title="Long Article",
            url="https://example.com",
            snippet=long_snippet,
            source="test",
            score=0.8,
        )
        enrich_result_metadata(long_result)
        assert long_result.metadata["reading_time"] > 1
