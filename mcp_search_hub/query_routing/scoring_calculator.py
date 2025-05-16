"""Advanced scoring calculator for provider selection."""

import math
from datetime import UTC, datetime

from ..models.query import QueryFeatures
from ..models.router import ProviderPerformanceMetrics, ProviderScore, ScoringMode
from ..providers.base import SearchProvider


class ScoringCalculator:
    """Calculates advanced scores for provider selection."""

    def __init__(self):
        # Default weights for different scoring components
        self.weights = {
            "feature_match": 0.4,
            "performance": 0.3,
            "recency": 0.2,
            "specialization": 0.1,
        }

        # Performance metric weights
        self.performance_weights = {
            "response_time": 0.3,
            "success_rate": 0.4,
            "result_quality": 0.3,
        }

        # Decay functions for time-sensitive queries
        self.recency_decay_hours = 24  # Hours before recency bonus decays

    def calculate_provider_score(
        self,
        provider_name: str,
        provider: SearchProvider,
        features: QueryFeatures,
        performance_metrics: ProviderPerformanceMetrics | None = None,
    ) -> ProviderScore:
        """Calculate comprehensive score for a provider."""
        capabilities = provider.get_capabilities()

        # Calculate base feature match score
        base_score = self._calculate_feature_match_score(
            provider_name, provider, features, capabilities
        )

        # Calculate performance score
        performance_score = self._calculate_performance_score(performance_metrics)

        # Calculate recency bonus for time-sensitive queries
        recency_bonus = self._calculate_recency_bonus(features, performance_metrics)

        # Calculate specialization bonus
        specialization_bonus = self._calculate_specialization_bonus(
            provider_name, features, capabilities
        )

        # Calculate confidence based on available data
        confidence = self._calculate_confidence(performance_metrics)

        # Calculate weighted score using advanced scoring function
        weighted_score = self._combine_scores(
            base_score=base_score,
            performance_score=performance_score,
            recency_bonus=recency_bonus,
            specialization_bonus=specialization_bonus,
        )

        # Generate explanation
        explanation = self._generate_explanation(
            provider_name,
            base_score,
            performance_score,
            recency_bonus,
            specialization_bonus,
            weighted_score,
        )

        return ProviderScore(
            provider_name=provider_name,
            base_score=base_score,
            performance_score=performance_score,
            recency_bonus=recency_bonus,
            confidence=confidence,
            weighted_score=weighted_score,
            explanation=explanation,
        )

    def _calculate_feature_match_score(
        self,
        provider_name: str,
        provider: SearchProvider,
        features: QueryFeatures,
        capabilities: dict,
    ) -> float:
        """Calculate base score based on feature matching."""
        score = 0.0

        # Content type matching with nuanced weights
        if features.content_type in capabilities.get("content_types", []):
            content_weights = {
                "academic": {"exa": 3.5, "perplexity": 2.5, "default": 2.0},
                "news": {
                    "perplexity": 3.5,
                    "tavily": 3.0,
                    "linkup": 2.5,
                    "default": 2.0,
                },
                "technical": {
                    "tavily": 3.0,
                    "linkup": 2.5,
                    "firecrawl": 2.0,
                    "default": 2.0,
                },
                "business": {
                    "linkup": 3.5,
                    "exa": 2.5,
                    "perplexity": 2.0,
                    "default": 2.0,
                },
                "web_content": {"firecrawl": 4.0, "tavily": 2.0, "default": 1.5},
                "general": {"tavily": 2.0, "linkup": 2.0, "default": 1.5},
            }
            weight = content_weights.get(features.content_type, {}).get(
                provider_name,
                content_weights.get(features.content_type, {}).get("default", 2.0),
            )
            score += weight

        # Complexity scoring - some providers handle complex queries better
        if features.complexity > 0.7:
            complexity_scores = {
                "exa": 2.0,  # Good semantic search
                "perplexity": 2.5,  # Excellent for complex reasoning
                "linkup": 1.5,
                "tavily": 1.5,
                "firecrawl": 1.0,
            }
            score += complexity_scores.get(provider_name, 1.0) * features.complexity

        # Time sensitivity scoring
        if features.time_sensitivity > 0.6:
            time_scores = {
                "perplexity": 3.0,  # Great for current events
                "linkup": 2.5,  # Good real-time data
                "tavily": 2.0,
                "exa": 1.5,
                "firecrawl": 1.0,
            }
            score += time_scores.get(provider_name, 1.0) * features.time_sensitivity

        # Factual nature scoring
        if features.factual_nature > 0.7:
            factual_scores = {
                "linkup": 2.5,  # Excellent for facts
                "exa": 2.0,  # Good for academic facts
                "perplexity": 2.0,
                "tavily": 1.5,
                "firecrawl": 1.0,
            }
            score += factual_scores.get(provider_name, 1.5) * features.factual_nature

        return score

    def _calculate_performance_score(
        self, metrics: ProviderPerformanceMetrics | None
    ) -> float:
        """Calculate performance score based on historical metrics."""
        if not metrics:
            return 1.0  # Default score when no metrics available

        # Normalize response time (faster is better)
        # Assume 1000ms is good, 5000ms is bad
        response_score = self._sigmoid(
            5000 - metrics.avg_response_time, k=1000, steepness=0.001
        )

        # Success rate is already normalized
        success_score = metrics.success_rate

        # Result quality is already normalized
        quality_score = metrics.avg_result_quality

        # Combine with weights
        return (
            self.performance_weights["response_time"] * response_score
            + self.performance_weights["success_rate"] * success_score
            + self.performance_weights["result_quality"] * quality_score
        )

    def _calculate_recency_bonus(
        self,
        features: QueryFeatures,
        metrics: ProviderPerformanceMetrics | None,
    ) -> float:
        """Calculate recency bonus for time-sensitive queries."""
        if features.time_sensitivity < 0.3:
            return 0.0

        # Base recency bonus
        bonus = features.time_sensitivity * 2.0

        # Apply decay if metrics are available
        if metrics and metrics.last_updated:
            try:
                last_updated = datetime.fromisoformat(
                    metrics.last_updated.rstrip("Z")
                ).replace(tzinfo=UTC)
                hours_ago = (datetime.now(UTC) - last_updated).total_seconds() / 3600
                decay_factor = math.exp(-hours_ago / self.recency_decay_hours)
                bonus *= decay_factor
            except (ValueError, TypeError):
                pass

        return bonus

    def _calculate_specialization_bonus(
        self, provider_name: str, features: QueryFeatures, capabilities: dict
    ) -> float:
        """Calculate bonus for provider specialization."""
        bonus = 0.0

        # Provider-specific specializations
        specializations = {
            "exa": {
                "academic": 1.5,
                "research": 1.5,
                "semantic_search": 1.2,
            },
            "perplexity": {
                "reasoning": 1.5,
                "current_events": 1.5,
                "complex_queries": 1.3,
            },
            "linkup": {
                "factual": 1.5,
                "business": 1.3,
                "premium_sources": 1.2,
            },
            "tavily": {
                "ai_optimized": 1.2,
                "general_purpose": 1.0,
            },
            "firecrawl": {
                "web_extraction": 2.0,
                "deep_crawl": 1.5,
                "structured_data": 1.3,
            },
        }

        provider_specs = specializations.get(provider_name, {})

        # Check content type specialization
        if features.content_type in provider_specs:
            bonus += provider_specs[features.content_type]

        # Check for complexity handling
        if features.complexity > 0.7 and "complex_queries" in provider_specs:
            bonus += provider_specs["complex_queries"] * features.complexity

        # Check for semantic search needs
        if "semantic_search" in provider_specs and features.contains_question:
            bonus += provider_specs["semantic_search"]

        return bonus

    def _calculate_confidence(
        self, metrics: ProviderPerformanceMetrics | None
    ) -> float:
        """Calculate confidence score based on available data."""
        if not metrics:
            return 0.5  # Medium confidence when no data

        # More queries = higher confidence
        query_confidence = min(metrics.total_queries / 1000, 1.0)

        # Success rate contributes to confidence
        success_confidence = metrics.success_rate

        # Combine factors
        return query_confidence * 0.6 + success_confidence * 0.4

    def _combine_scores(
        self,
        base_score: float,
        performance_score: float,
        recency_bonus: float,
        specialization_bonus: float,
    ) -> float:
        """Combine different score components using weighted approach."""
        # Normalize scores before combining
        normalized_scores = {
            "base": self._normalize_score(base_score, max_value=10.0),
            "performance": performance_score,  # Already normalized
            "recency": self._normalize_score(recency_bonus, max_value=5.0),
            "specialization": self._normalize_score(
                specialization_bonus, max_value=5.0
            ),
        }

        # Apply weights
        return (
            self.weights["feature_match"] * normalized_scores["base"]
            + self.weights["performance"] * normalized_scores["performance"]
            + self.weights["recency"] * normalized_scores["recency"]
            + self.weights["specialization"] * normalized_scores["specialization"]
        )

    def _sigmoid(self, x: float, k: float = 0.0, steepness: float = 1.0) -> float:
        """Sigmoid function for smooth transitions."""
        try:
            return 1 / (1 + math.exp(-steepness * (x - k)))
        except OverflowError:
            # Handle extreme values
            # If exponent is positive (math.exp will overflow), sigmoid approaches 0
            # If exponent is negative (math.exp underflows), sigmoid approaches 1
            if steepness * (x - k) > 0:
                return 1.0
            return 0.0

    def _normalize_score(self, score: float, max_value: float = 10.0) -> float:
        """Normalize score to 0-1 range."""
        return min(score / max_value, 1.0)

    def _generate_explanation(
        self,
        provider_name: str,
        base_score: float,
        performance_score: float,
        recency_bonus: float,
        specialization_bonus: float,
        weighted_score: float,
    ) -> str:
        """Generate human-readable explanation of scoring."""
        explanation_parts = [f"{provider_name} scored {weighted_score:.3f}:"]

        if base_score > 0:
            explanation_parts.append(f"- Feature match: {base_score:.2f}")

        if performance_score != 1.0:
            explanation_parts.append(f"- Performance: {performance_score:.2f}")

        if recency_bonus > 0:
            explanation_parts.append(f"- Recency bonus: {recency_bonus:.2f}")

        if specialization_bonus > 0:
            explanation_parts.append(f"- Specialization: {specialization_bonus:.2f}")

        return " ".join(explanation_parts)

    def combine_scores_by_mode(
        self, scores: list[float], mode: ScoringMode = ScoringMode.AVG
    ) -> float:
        """Combine multiple scores using specified mode."""
        if not scores:
            return 0.0

        if mode == ScoringMode.MAX:
            return max(scores)
        if mode == ScoringMode.SUM:
            return sum(scores)
        if mode == ScoringMode.MULTIPLY:
            result = 1.0
            for score in scores:
                result *= score
            return result
        # AVG
        return sum(scores) / len(scores)
