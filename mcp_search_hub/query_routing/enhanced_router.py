"""Enhanced query router with advanced scoring and confidence measurement."""

from ..models.query import QueryFeatures, SearchQuery
from ..models.router import (
    ProviderPerformanceMetrics,
    ProviderScore,
    RoutingDecision,
    ScoringMode,
)
from ..providers.base import SearchProvider
from .cost_optimizer import CostOptimizer
from .scoring_calculator import ScoringCalculator


class EnhancedQueryRouter:
    """Routes queries to appropriate search providers with enhanced scoring."""

    def __init__(
        self,
        providers: dict[str, SearchProvider],
        performance_metrics: dict[str, ProviderPerformanceMetrics] | None = None,
    ):
        self.providers = providers
        self.cost_optimizer = CostOptimizer()
        self.scoring_calculator = ScoringCalculator()
        self.performance_metrics = performance_metrics or {}

    def select_providers(
        self,
        query: SearchQuery,
        features: QueryFeatures,
        budget: float | None = None,
        mode: ScoringMode = ScoringMode.AVG,
    ) -> RoutingDecision:
        """Select the best provider(s) for a query using enhanced scoring."""
        provider_scores = []

        # Calculate scores for each provider
        for name, provider in self.providers.items():
            metrics = self.performance_metrics.get(name)
            score = self.scoring_calculator.calculate_provider_score(
                name, provider, features, metrics
            )
            provider_scores.append(score)

        # Sort by weighted score
        provider_scores.sort(key=lambda x: x.weighted_score, reverse=True)

        # Select providers based on budget or score threshold
        if budget is not None:
            # Use cost-aware selection
            selected_providers = self._select_with_budget(
                query, provider_scores, budget
            )
        else:
            # Select based on score threshold and confidence
            selected_providers = self._select_by_score_threshold(provider_scores)

        # Calculate overall confidence
        overall_confidence = self._calculate_overall_confidence(
            selected_providers, provider_scores
        )

        # Generate decision explanation
        explanation = self._generate_decision_explanation(
            selected_providers, provider_scores, budget
        )

        return RoutingDecision(
            query_id=query.query,  # Using query text as ID for now
            selected_providers=selected_providers,
            provider_scores=provider_scores,
            score_mode=mode,
            confidence=overall_confidence,
            explanation=explanation,
            metadata={
                "budget": budget,
                "features": features.model_dump(),
            },
        )

    def _select_with_budget(
        self,
        query: SearchQuery,
        provider_scores: list[ProviderScore],
        budget: float,
    ) -> list[str]:
        """Select providers considering budget constraints."""
        # Convert scores to dict format for cost optimizer
        score_dict = {
            score.provider_name: score.weighted_score for score in provider_scores
        }

        return self.cost_optimizer.optimize_selection(
            query, self.providers, score_dict, budget
        )

    def _select_by_score_threshold(
        self, provider_scores: list[ProviderScore]
    ) -> list[str]:
        """Select providers based on score threshold and confidence."""
        if not provider_scores:
            return []

        selected = []
        top_score = provider_scores[0].weighted_score

        # Select top provider
        selected.append(provider_scores[0].provider_name)

        # Select additional providers if they meet criteria
        for score in provider_scores[1:]:
            # Include if score is close to top score (within 20%)
            if score.weighted_score >= top_score * 0.8:
                # And if confidence is reasonable
                if score.confidence >= 0.6:
                    selected.append(score.provider_name)
            else:
                break

            # Limit to 3 providers
            if len(selected) >= 3:
                break

        return selected

    def _calculate_overall_confidence(
        self,
        selected_providers: list[str],
        provider_scores: list[ProviderScore],
    ) -> float:
        """Calculate overall confidence in the routing decision."""
        if not selected_providers:
            return 0.0

        # Get scores for selected providers
        selected_scores = [
            score
            for score in provider_scores
            if score.provider_name in selected_providers
        ]

        # Calculate confidence based on multiple factors
        confidences = []

        # 1. Average confidence of selected providers
        avg_confidence = sum(s.confidence for s in selected_scores) / len(
            selected_scores
        )
        confidences.append(avg_confidence)

        # 2. Score separation (how clearly the top providers stand out)
        if len(provider_scores) > 1:
            score_gap = (
                selected_scores[0].weighted_score - provider_scores[-1].weighted_score
            )
            separation_confidence = min(score_gap / 0.5, 1.0)  # 0.5 is good separation
            confidences.append(separation_confidence)

        # 3. Consistency among selected providers
        if len(selected_scores) > 1:
            score_variance = self._calculate_variance(
                [s.weighted_score for s in selected_scores]
            )
            consistency_confidence = 1.0 - min(score_variance / 0.1, 1.0)
            confidences.append(consistency_confidence)

        # Combine confidences
        return sum(confidences) / len(confidences)

    def _calculate_variance(self, values: list[float]) -> float:
        """Calculate variance of a list of values."""
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        return sum((x - mean) ** 2 for x in values) / len(values)

    def _generate_decision_explanation(
        self,
        selected_providers: list[str],
        provider_scores: list[ProviderScore],
        budget: float | None,
    ) -> str:
        """Generate explanation for the routing decision."""
        parts = [f"Selected {len(selected_providers)} provider(s):"]

        # Add top provider explanation
        if provider_scores:
            top_score = provider_scores[0]
            parts.append(
                f"Primary: {top_score.provider_name} "
                f"(score: {top_score.weighted_score:.3f}, "
                f"confidence: {top_score.confidence:.2f})"
            )

        # Add secondary providers
        for provider in selected_providers[1:]:
            score = next(s for s in provider_scores if s.provider_name == provider)
            parts.append(
                f"Secondary: {provider} "
                f"(score: {score.weighted_score:.3f}, "
                f"confidence: {score.confidence:.2f})"
            )

        # Add budget consideration
        if budget is not None:
            parts.append(f"Budget constraint: ${budget:.2f}")

        return " | ".join(parts)

    def update_performance_metrics(
        self, provider_name: str, metrics: ProviderPerformanceMetrics
    ):
        """Update performance metrics for a provider."""
        self.performance_metrics[provider_name] = metrics

    def get_provider_ranking(self, features: QueryFeatures) -> list[ProviderScore]:
        """Get ranking of all providers for given query features."""
        scores = []

        for name, provider in self.providers.items():
            metrics = self.performance_metrics.get(name)
            score = self.scoring_calculator.calculate_provider_score(
                name, provider, features, metrics
            )
            scores.append(score)

        scores.sort(key=lambda x: x.weighted_score, reverse=True)
        return scores
