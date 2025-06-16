"""Tests for the LLM routing functionality."""

import os
from unittest import mock

from mcp_search_hub.models.query import QueryFeatures
from mcp_search_hub.models.router import ProviderScore
from mcp_search_hub.providers.base import SearchProvider
from mcp_search_hub.query_routing.llm_router import (
    LLMQueryRouter,
    LLMRoutingResult,
    RoutingHintParser,
)
from mcp_search_hub.utils.cache import TimedCache


class TestLLMQueryRouter:
    """Test the LLM query router functionality."""

    def setup_method(self):
        """Set up test environment."""
        # Mock environment variables
        self.env_patcher = mock.patch.dict(
            os.environ,
            {
                "LLM_ROUTER_ENABLED": "true",
                "LLM_ROUTER_THRESHOLD": "0.5",
                "LLM_ROUTER_CACHE_TTL": "60",
            },
        )
        self.env_patcher.start()

        # Create test objects
        self.llm_router = LLMQueryRouter()
        self.fallback_scorer = mock.MagicMock()
        self.fallback_scorer.score_provider.return_value = ProviderScore(
            provider_name="test_provider",
            base_score=0.5,
            weighted_score=0.5,
            confidence=0.5,
            explanation="Fallback scoring",
            features_match={},
        )
        self.llm_router_with_fallback = LLMQueryRouter(
            fallback_scorer=self.fallback_scorer
        )

        # Create test provider
        self.provider = mock.MagicMock(spec=SearchProvider)
        self.provider.name = "test_provider"

        # Create test query features
        self.features = QueryFeatures(
            length=20,
            word_count=4,
            contains_question=True,
            content_type="web_search",
            time_sensitivity=0.3,
            complexity=0.7,
            factual_nature=0.8,
        )

        # Create test simple features (below threshold)
        self.simple_features = QueryFeatures(
            length=10,
            word_count=2,
            contains_question=False,
            content_type="web_search",
            time_sensitivity=0.1,
            complexity=0.3,
            factual_nature=0.5,
        )

    def teardown_method(self):
        """Clean up test environment."""
        self.env_patcher.stop()

    def test_init(self):
        """Test initialization."""
        assert self.llm_router.fallback_scorer is None
        assert isinstance(self.llm_router.cache, TimedCache)
        assert self.llm_router.metrics["llm_calls"] == 0
        assert self.llm_router.metrics["cache_hits"] == 0
        assert self.llm_router.metrics["fallback_used"] == 0

        # Test with fallback scorer
        assert self.llm_router_with_fallback.fallback_scorer == self.fallback_scorer

    @mock.patch("mcp_search_hub.query_routing.llm_router.LLM_ROUTER_ENABLED", False)
    def test_score_provider_disabled(self):
        """Test scoring when LLM router is disabled."""
        # Create a new router with disabled flag
        router = LLMQueryRouter(fallback_scorer=self.fallback_scorer)

        # Call score_provider
        result = router.score_provider("test_provider", self.provider, self.features)

        # Verify fallback was used
        assert result == self.fallback_scorer.score_provider.return_value
        self.fallback_scorer.score_provider.assert_called_once_with(
            "test_provider", self.provider, self.features, None
        )

    def test_score_provider_below_threshold(self):
        """Test scoring when query complexity is below threshold."""
        # Call score_provider with simple features
        result = self.llm_router_with_fallback.score_provider(
            "test_provider", self.provider, self.simple_features
        )

        # Verify fallback was used
        assert result == self.fallback_scorer.score_provider.return_value
        self.fallback_scorer.score_provider.assert_called_once_with(
            "test_provider", self.provider, self.simple_features, None
        )

    @mock.patch("mcp_search_hub.query_routing.llm_router.LLM_ROUTER_ENABLED", True)
    @mock.patch(
        "mcp_search_hub.query_routing.llm_router.LLMQueryRouter._call_llm_for_routing"
    )
    def test_score_provider_with_llm(self, mock_call_llm):
        """Test scoring with LLM."""
        # Set up mock LLM response
        mock_result = LLMRoutingResult(
            provider_scores={"test_provider": 0.8},
            confidence=0.9,
            explanation="Test explanation",
            routing_strategy="cascade",
        )
        mock_call_llm.return_value = mock_result

        # Call score_provider
        result = self.llm_router.score_provider(
            "test_provider", self.provider, self.features
        )

        # Verify result
        assert result.provider_name == "test_provider"
        assert result.base_score == 0.8
        assert result.weighted_score == 0.8
        assert result.confidence == 0.9
        assert result.explanation == "Test explanation"

        # Verify LLM was called
        mock_call_llm.assert_called_once_with(self.features)

    @mock.patch("mcp_search_hub.query_routing.llm_router.LLM_ROUTER_ENABLED", True)
    @mock.patch(
        "mcp_search_hub.query_routing.llm_router.LLMQueryRouter._call_llm_for_routing"
    )
    def test_cache_usage(self, mock_call_llm):
        """Test cache functionality."""
        # Set up mock LLM response
        mock_result = LLMRoutingResult(
            provider_scores={"test_provider": 0.8},
            confidence=0.9,
            explanation="Test explanation",
            routing_strategy="cascade",
        )
        mock_call_llm.return_value = mock_result

        # First call should use LLM
        self.llm_router.score_provider("test_provider", self.provider, self.features)
        assert mock_call_llm.call_count == 1
        assert self.llm_router.metrics["llm_calls"] == 1
        assert self.llm_router.metrics["cache_hits"] == 0

        # Second call with same features should use cache
        self.llm_router.score_provider("test_provider", self.provider, self.features)
        assert mock_call_llm.call_count == 1  # No additional calls
        assert self.llm_router.metrics["llm_calls"] == 1
        assert self.llm_router.metrics["cache_hits"] == 1

    @mock.patch("mcp_search_hub.query_routing.llm_router.LLM_ROUTER_ENABLED", True)
    @mock.patch(
        "mcp_search_hub.query_routing.llm_router.LLMQueryRouter._call_llm_for_routing"
    )
    def test_fallback_on_error(self, mock_call_llm):
        """Test fallback when LLM call raises an exception."""
        # Set up mock LLM to raise an exception
        mock_call_llm.side_effect = Exception("Test error")

        # Call score_provider
        result = self.llm_router_with_fallback.score_provider(
            "test_provider", self.provider, self.features
        )

        # Verify fallback was used
        assert result == self.fallback_scorer.score_provider.return_value
        assert self.llm_router_with_fallback.metrics["fallback_used"] == 1

    def test_create_cache_key(self):
        """Test cache key creation."""
        # Create two identical features objects
        features1 = QueryFeatures(
            length=20,
            word_count=4,
            contains_question=True,
            content_type="web_search",
            time_sensitivity=0.3,
            complexity=0.7,
            factual_nature=0.8,
        )
        features2 = QueryFeatures(
            length=20,
            word_count=4,
            contains_question=True,
            content_type="web_search",
            time_sensitivity=0.3,
            complexity=0.7,
            factual_nature=0.8,
        )

        # Keys should be identical
        key1 = self.llm_router._create_cache_key(features1)
        key2 = self.llm_router._create_cache_key(features2)
        assert key1 == key2

        # Change a feature and verify key changes
        features2.complexity = 0.8
        key3 = self.llm_router._create_cache_key(features2)
        assert key1 != key3

    def test_call_llm_for_routing(self):
        """Test LLM calling logic."""
        # Just verify it returns a valid result structure for now
        # In a real test, we'd mock the actual LLM client
        result = self.llm_router._call_llm_for_routing(self.features)

        assert isinstance(result, LLMRoutingResult)
        assert "tavily" in result.provider_scores
        assert "perplexity" in result.provider_scores
        assert "linkup" in result.provider_scores
        assert "firecrawl" in result.provider_scores
        assert "exa" in result.provider_scores
        assert 0 <= result.confidence <= 1.0
        assert result.explanation
        assert result.routing_strategy in ["parallel", "cascade"]


class TestRoutingHintParser:
    """Test the routing hint parser functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.parser = RoutingHintParser()

    def test_parse_academic_hints(self):
        """Test parsing academic/research related hints."""
        hints = "I need academic research on this topic"
        params = self.parser.parse_hints(hints)

        assert "preferred_providers" in params
        assert "perplexity" in params["preferred_providers"]
        assert "exa" in params["preferred_providers"]

    def test_parse_news_hints(self):
        """Test parsing news/recent related hints."""
        hints = "Find the most recent news on this subject"
        params = self.parser.parse_hints(hints)

        assert "preferred_providers" in params
        assert "tavily" in params["preferred_providers"]
        assert "linkup" in params["preferred_providers"]

    def test_parse_image_hints(self):
        """Test parsing image/visual related hints."""
        hints = "I need visual information about this"
        params = self.parser.parse_hints(hints)

        assert "preferred_providers" in params
        assert "firecrawl" in params["preferred_providers"]
        assert "tavily" in params["preferred_providers"]

    def test_parse_reliability_hints(self):
        """Test parsing reliability related hints."""
        hints = "I need thorough and reliable information"
        params = self.parser.parse_hints(hints)

        assert "strategy" in params
        assert params["strategy"] == "cascade"
        assert "require_all_results" in params
        assert params["require_all_results"] is True

    def test_parse_speed_hints(self):
        """Test parsing speed related hints."""
        hints = "I need fast results"
        params = self.parser.parse_hints(hints)

        assert "strategy" in params
        assert params["strategy"] == "parallel"
        assert "require_all_results" in params
        assert params["require_all_results"] is False

    def test_parse_combined_hints(self):
        """Test parsing combined hints."""
        hints = "Need fast academic research"
        params = self.parser.parse_hints(hints)

        assert "preferred_providers" in params
        assert "perplexity" in params["preferred_providers"]
        assert "strategy" in params
        assert params["strategy"] == "parallel"

    def test_parse_empty_hints(self):
        """Test parsing empty hints."""
        hints = ""
        params = self.parser.parse_hints(hints)

        assert params == {}
