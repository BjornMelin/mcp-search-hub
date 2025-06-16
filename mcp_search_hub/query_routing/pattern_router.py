"""Pattern-based router for Tier 2 routing.

This module provides advanced pattern matching and feature-based routing
for medium complexity queries. It uses the SimpleContentDetector and
additional patterns to make routing decisions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..models.query import SearchQuery
from ..providers.base import SearchProvider
from .simple_analyzer import SimpleContentDetector

logger = logging.getLogger(__name__)


@dataclass
class PatternScore:
    """Score for a provider based on pattern matching."""

    provider: str
    content_match: float
    feature_match: float
    total_score: float
    reasons: list[str]


class PatternRouter:
    """Advanced pattern-based router for medium complexity queries.

    This router uses content detection, query features, and pattern
    matching to route queries with <10ms latency.
    """

    def __init__(self, providers: dict[str, SearchProvider]):
        """Initialize the pattern router.

        Args:
            providers: Available search providers
        """
        self.providers = providers
        self.content_detector = SimpleContentDetector()

        # Provider strengths by content type
        self.content_type_providers = {
            "news": {
                "primary": ["linkup", "tavily"],
                "secondary": ["perplexity"],
                "boost": 1.5,
            },
            "technical": {
                "primary": ["perplexity", "firecrawl"],
                "secondary": ["exa", "tavily"],
                "boost": 1.3,
            },
            "academic": {
                "primary": ["exa", "perplexity"],
                "secondary": ["tavily"],
                "boost": 1.4,
            },
            "commercial": {
                "primary": ["tavily", "perplexity"],
                "secondary": ["linkup"],
                "boost": 1.2,
            },
            "general": {
                "primary": ["tavily", "perplexity", "linkup"],
                "secondary": ["exa"],
                "boost": 1.0,
            },
        }

        # Feature-based provider selection
        self.feature_providers = {
            "question": {
                "providers": ["perplexity", "tavily"],
                "boost": 1.2,
            },
            "comparison": {
                "providers": ["perplexity", "exa"],
                "boost": 1.3,
            },
            "tutorial": {
                "providers": ["firecrawl", "perplexity"],
                "boost": 1.3,
            },
            "list": {
                "providers": ["tavily", "linkup"],
                "boost": 1.1,
            },
            "definition": {
                "providers": ["tavily", "perplexity"],
                "boost": 1.2,
            },
        }

        # Query length preferences
        self.length_preferences = {
            "short": ["tavily", "linkup"],  # Fast, direct answers
            "medium": ["perplexity", "tavily"],  # Balanced
            "long": ["perplexity", "exa"],  # Complex analysis
        }

    async def route(self, query: SearchQuery) -> list[str]:
        """Route query based on patterns and features.

        Args:
            query: The search query

        Returns:
            List of selected provider names
        """
        # Detect content type
        content_type = self.content_detector.detect_content_type(query.query)

        # Extract query features
        is_question = self.content_detector.is_question(query.query)
        query_length = self.content_detector.get_query_length_category(query.query)
        entities = self.content_detector.extract_key_entities(query.query)

        # Score each provider
        provider_scores = {}

        for provider in self.providers:
            score = PatternScore(
                provider=provider,
                content_match=0.0,
                feature_match=0.0,
                total_score=0.0,
                reasons=[],
            )

            # Score based on content type
            content_config = self.content_type_providers.get(content_type, {})
            if provider in content_config.get("primary", []):
                score.content_match = 1.0 * content_config.get("boost", 1.0)
                score.reasons.append(f"Primary for {content_type} content")
            elif provider in content_config.get("secondary", []):
                score.content_match = 0.6 * content_config.get("boost", 1.0)
                score.reasons.append(f"Secondary for {content_type} content")

            # Score based on query features
            if (
                is_question
                and provider in self.feature_providers["question"]["providers"]
            ):
                score.feature_match += 0.3 * self.feature_providers["question"]["boost"]
                score.reasons.append("Good for questions")

            # Check for specific patterns
            query_lower = query.query.lower()
            if (
                "compare" in query_lower or "vs" in query_lower
            ) and provider in self.feature_providers["comparison"]["providers"]:
                score.feature_match += (
                    0.4 * self.feature_providers["comparison"]["boost"]
                )
                score.reasons.append("Excels at comparisons")

            if (
                "how to" in query_lower or "tutorial" in query_lower
            ) and provider in self.feature_providers["tutorial"]["providers"]:
                score.feature_match += 0.4 * self.feature_providers["tutorial"]["boost"]
                score.reasons.append("Good for tutorials")

            if (
                "list of" in query_lower or "top" in query_lower
            ) and provider in self.feature_providers["list"]["providers"]:
                score.feature_match += 0.3 * self.feature_providers["list"]["boost"]
                score.reasons.append("Good for lists")

            # Score based on query length
            if provider in self.length_preferences.get(query_length, []):
                score.feature_match += 0.2
                score.reasons.append(f"Suitable for {query_length} queries")

            # Bonus for entity extraction
            if entities and provider in ["exa", "perplexity"]:
                score.feature_match += 0.1 * len(entities)
                score.reasons.append("Good with specific entities")

            # Calculate total score
            score.total_score = score.content_match + score.feature_match

            if score.total_score > 0:
                provider_scores[provider] = score

        # Sort by total score
        sorted_providers = sorted(
            provider_scores.items(), key=lambda x: x[1].total_score, reverse=True
        )

        # Select top providers
        selected = []
        for provider, score in sorted_providers:
            if score.total_score > 0.8 or len(selected) < 3:
                selected.append(provider)
                logger.debug(
                    f"Selected {provider} (score: {score.total_score:.2f}) "
                    f"for: {', '.join(score.reasons)}"
                )
            if len(selected) >= 5:  # Max 5 providers
                break

        # Fallback if no good matches
        if not selected:
            selected = ["tavily", "perplexity", "linkup"]
            selected = [p for p in selected if p in self.providers]

        return selected

    async def score_provider(
        self,
        provider_name: str,
        provider: SearchProvider,
        features: dict,
    ) -> PatternScore:
        """Score a single provider for given features.

        This method is used by the LLM router as a fallback scorer.

        Args:
            provider_name: Name of the provider
            provider: Provider instance
            features: Query features

        Returns:
            PatternScore for the provider
        """
        # Create a synthetic query for the content detector
        from ..models.query import SearchQuery

        query = SearchQuery(query=features.get("query", ""))

        # Route and find this provider's score
        providers = await self.route(query)

        if provider_name in providers:
            # Provider was selected, give it a good score
            position = providers.index(provider_name)
            base_score = 1.0 - (position * 0.1)  # Top provider gets 1.0
            return PatternScore(
                provider=provider_name,
                content_match=base_score * 0.6,
                feature_match=base_score * 0.4,
                total_score=base_score,
                reasons=["Selected by pattern matching"],
            )
        # Provider not selected
        return PatternScore(
            provider=provider_name,
            content_match=0.2,
            feature_match=0.1,
            total_score=0.3,
            reasons=["Not optimal for this query"],
        )
