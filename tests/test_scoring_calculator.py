"""Tests for the scoring calculator."""

import pytest

from mcp_search_hub.models.query import QueryFeatures
from mcp_search_hub.models.router import ProviderPerformanceMetrics
from mcp_search_hub.query_routing.scoring_calculator import ScoringCalculator


class MockProvider:
    """Mock provider for testing."""

    def __init__(self, capabilities):
        self.capabilities = capabilities

    def get_capabilities(self):
        return self.capabilities


class TestScoringCalculator:
    """Test the scoring calculator."""

    @pytest.fixture
    def calculator(self):
        return ScoringCalculator()

    def test_feature_match_scoring_academic(self, calculator):
        """Test feature match scoring for academic content."""
        provider = MockProvider({"content_types": ["academic", "general"]})
        features = QueryFeatures(
            content_type="academic",
            length=50,
            word_count=8,
            contains_question=True,
            time_sensitivity=0.2,
            complexity=0.9,
            factual_nature=0.95,
        )

        # Test Exa (should score high for academic)
        score = calculator._calculate_feature_match_score(
            "exa", provider, features, provider.get_capabilities()
        )
        assert score > 5.0  # High score for academic content

        # Test complexity bonus
        assert score > 6.0  # Should get complexity bonus

    def test_feature_match_scoring_news(self, calculator):
        """Test feature match scoring for news content."""
        provider = MockProvider({"content_types": ["news", "general"]})
        features = QueryFeatures(
            content_type="news",
            length=40,
            word_count=6,
            contains_question=False,
            time_sensitivity=0.9,
            complexity=0.4,
            factual_nature=0.7,
        )

        # Test Perplexity (should score high for news)
        score = calculator._calculate_feature_match_score(
            "perplexity", provider, features, provider.get_capabilities()
        )
        assert score > 5.0  # High score for news with time sensitivity

    def test_performance_score_calculation(self, calculator):
        """Test performance score calculation."""
        # Good performance metrics
        good_metrics = ProviderPerformanceMetrics(
            provider_name="test",
            avg_response_time=800.0,
            success_rate=0.98,
            avg_result_quality=0.92,
            total_queries=1000,
        )

        score = calculator._calculate_performance_score(good_metrics)
        assert score > 0.9  # Should be high for good metrics

        # Poor performance metrics
        poor_metrics = ProviderPerformanceMetrics(
            provider_name="test",
            avg_response_time=4000.0,
            success_rate=0.70,
            avg_result_quality=0.60,
            total_queries=100,
        )

        poor_score = calculator._calculate_performance_score(poor_metrics)
        assert poor_score < 0.7  # Should be lower for poor metrics
        assert poor_score < score  # Poor should be less than good

        # No metrics
        no_metrics_score = calculator._calculate_performance_score(None)
        assert no_metrics_score == 1.0  # Default score

    def test_recency_bonus_calculation(self, calculator):
        """Test recency bonus calculation."""
        # High time sensitivity
        features_high = QueryFeatures(
            content_type="news",
            length=30,
            word_count=5,
            contains_question=False,
            time_sensitivity=0.9,
            complexity=0.5,
            factual_nature=0.7,
        )

        bonus_high = calculator._calculate_recency_bonus(features_high, None)
        assert bonus_high > 1.0  # Should get significant bonus

        # Low time sensitivity
        features_low = QueryFeatures(
            content_type="academic",
            length=30,
            word_count=5,
            contains_question=False,
            time_sensitivity=0.2,
            complexity=0.5,
            factual_nature=0.7,
        )

        bonus_low = calculator._calculate_recency_bonus(features_low, None)
        assert bonus_low == 0.0  # No bonus for low time sensitivity

    def test_specialization_bonus(self, calculator):
        """Test specialization bonus calculation."""
        # Academic specialization for Exa
        academic_features = QueryFeatures(
            content_type="academic",
            length=50,
            word_count=8,
            contains_question=True,
            time_sensitivity=0.2,
            complexity=0.9,
            factual_nature=0.95,
        )

        exa_bonus = calculator._calculate_specialization_bonus(
            "exa", academic_features, {"content_types": ["academic"]}
        )
        assert exa_bonus >= 1.5  # Should get specialization bonus

        # Web content for Firecrawl
        web_features = QueryFeatures(
            content_type="web_content",
            length=30,
            word_count=5,
            contains_question=False,
            time_sensitivity=0.1,
            complexity=0.2,
            factual_nature=0.5,
        )

        firecrawl_bonus = calculator._calculate_specialization_bonus(
            "firecrawl", web_features, {"content_types": ["web_content"]}
        )
        # Firecrawl doesn't have a "web_content" specialization, only "web_extraction"
        # So it should get no bonus for this content type
        assert firecrawl_bonus == 0.0

    def test_confidence_calculation(self, calculator):
        """Test confidence score calculation."""
        # High confidence (lots of data)
        high_data_metrics = ProviderPerformanceMetrics(
            provider_name="test",
            avg_response_time=1000.0,
            success_rate=0.95,
            avg_result_quality=0.90,
            total_queries=5000,
        )

        high_confidence = calculator._calculate_confidence(high_data_metrics)
        assert high_confidence > 0.8

        # Low confidence (little data)
        low_data_metrics = ProviderPerformanceMetrics(
            provider_name="test",
            avg_response_time=1000.0,
            success_rate=0.85,
            avg_result_quality=0.80,
            total_queries=50,
        )

        low_confidence = calculator._calculate_confidence(low_data_metrics)
        assert low_confidence < 0.6

        # No metrics
        no_metrics_confidence = calculator._calculate_confidence(None)
        assert no_metrics_confidence == 0.5  # Default medium confidence

    def test_score_combination(self, calculator):
        """Test combining different score components."""
        combined = calculator._combine_scores(
            base_score=8.0,
            performance_score=0.9,
            recency_bonus=1.5,
            specialization_bonus=2.0,
        )

        # Should be normalized and weighted
        assert 0.0 <= combined <= 1.0

    def test_sigmoid_function(self, calculator):
        """Test sigmoid function behavior."""
        # Test basic sigmoid
        assert calculator._sigmoid(0) == 0.5
        assert calculator._sigmoid(1000) > 0.9
        assert calculator._sigmoid(-1000) < 0.1

        # Test with different parameters
        steep = calculator._sigmoid(2, k=1, steepness=2.0)
        gentle = calculator._sigmoid(2, k=1, steepness=0.5)
        assert steep > gentle  # Steeper curve should give higher value at x>k

    def test_normalize_score(self, calculator):
        """Test score normalization."""
        assert calculator._normalize_score(5.0, max_value=10.0) == 0.5
        assert calculator._normalize_score(15.0, max_value=10.0) == 1.0  # Capped at 1
        assert calculator._normalize_score(0.0, max_value=10.0) == 0.0

    def test_comprehensive_scoring(self, calculator):
        """Test full scoring process."""
        provider = MockProvider({"content_types": ["academic", "general"]})
        features = QueryFeatures(
            content_type="academic",
            length=60,
            word_count=10,
            contains_question=True,
            time_sensitivity=0.3,
            complexity=0.85,
            factual_nature=0.9,
        )

        metrics = ProviderPerformanceMetrics(
            provider_name="exa",
            avg_response_time=1200.0,
            success_rate=0.94,
            avg_result_quality=0.88,
            total_queries=1200,
        )

        score = calculator.calculate_provider_score("exa", provider, features, metrics)

        # Check all components are calculated
        assert score.base_score > 0
        assert score.performance_score > 0
        assert score.confidence > 0
        assert score.weighted_score > 0
        assert score.explanation

        # Weighted score should be reasonable
        assert 0.0 <= score.weighted_score <= 1.0
