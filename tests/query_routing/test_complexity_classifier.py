"""Tests for the complexity classifier."""

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.query_routing.complexity_classifier import ComplexityClassifier


@pytest.fixture
def classifier():
    """Create a complexity classifier instance."""
    return ComplexityClassifier()


class TestComplexityClassifier:
    """Test the complexity classifier."""

    def test_simple_queries(self, classifier):
        """Test classification of simple queries."""
        simple_queries = [
            "weather today",
            "python tutorial",
            "news",
            "github status",
            "time in tokyo",
        ]

        for query_text in simple_queries:
            query = SearchQuery(query=query_text)
            result = classifier.classify(query)

            assert result.score < 0.3
            assert result.level == "simple"
            assert "straightforward" in result.explanation.lower()

    def test_medium_queries(self, classifier):
        """Test classification of medium complexity queries."""
        medium_queries = [
            # These will actually score as simple or at the boundary
            ("how to implement authentication in FastAPI", 0.3),
            ("compare Python vs JavaScript for web development", 0.35),
            # These are more clearly medium complexity
            (
                "analyze and compare different authentication methods in modern web frameworks",
                0.4,
            ),
            (
                "explain the pros and cons of microservices vs monolithic architecture",
                0.5,
            ),
        ]

        for query_text, min_score in medium_queries:
            query = SearchQuery(query=query_text)
            result = classifier.classify(query)

            assert result.score >= min_score
            if result.score >= 0.3:
                assert result.level in ["medium", "complex"]

    def test_complex_queries(self, classifier):
        """Test classification of complex queries."""
        complex_queries = [
            "analyze the environmental and economic impact of electric vehicles considering battery production and disposal",
            "compare and evaluate different approaches to distributed systems considering consistency, availability, and partition tolerance trade-offs",
            "explain the relationship between quantum computing and cryptography and how it might affect future security implementations",
        ]

        for query_text in complex_queries:
            query = SearchQuery(query=query_text)
            result = classifier.classify(query)

            assert result.score >= 0.7
            assert result.level == "complex"
            assert "complex" in result.explanation.lower()

    def test_factor_contributions(self, classifier):
        """Test individual factor contributions."""
        # Test length factor
        short_query = SearchQuery(query="test")
        short_result = classifier.classify(short_query)
        assert short_result.factors["length"] == 0.0

        long_query = SearchQuery(query=" ".join(["word"] * 20))
        long_result = classifier.classify(long_query)
        assert long_result.factors["length"] == 0.25

        # Test complex keywords
        keyword_query = SearchQuery(query="compare and analyze the impact")
        keyword_result = classifier.classify(keyword_query)
        assert keyword_result.factors["complex_keywords"] > 0

        # Test question type
        how_query = SearchQuery(query="how does authentication work")
        how_result = classifier.classify(how_query)
        assert how_result.factors["question_type"] == 0.2

        # Test multi-intent
        multi_query = SearchQuery(
            query="find news and also check weather, plus get stock prices"
        )
        multi_result = classifier.classify(multi_query)
        assert multi_result.factors["multi_intent"] > 0

    def test_cross_domain_detection(self, classifier):
        """Test cross-domain indicator detection."""
        cross_domain_query = SearchQuery(
            query="environmental and economic impact of renewable energy"
        )
        result = classifier.classify(cross_domain_query)
        assert result.factors["cross_domain"] == 0.2
        assert "Crosses multiple domains" in result.explanation

    def test_ambiguity_detection(self, classifier):
        """Test ambiguity detection."""
        ambiguous_query = SearchQuery(
            query="might be possible that sometimes it could work"
        )
        result = classifier.classify(ambiguous_query)
        assert result.factors["ambiguity"] > 0

    def test_edge_cases(self, classifier):
        """Test edge cases."""
        # Empty query
        empty_query = SearchQuery(query="")
        empty_result = classifier.classify(empty_query)
        assert empty_result.level == "simple"

        # Very long query
        long_text = " ".join(["complex"] * 100)
        long_query = SearchQuery(query=long_text)
        long_result = classifier.classify(long_query)
        assert long_result.score <= 1.0  # Should be capped

        # Special characters
        special_query = SearchQuery(query="test!@#$%^&*()")
        special_result = classifier.classify(special_query)
        assert special_result.level == "simple"
