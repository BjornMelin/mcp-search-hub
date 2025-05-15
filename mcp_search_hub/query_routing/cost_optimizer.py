"""Cost optimization strategies."""

from typing import Dict, List

from ..models.query import SearchQuery
from ..providers.base import SearchProvider


class CostOptimizer:
    """Optimizes provider selection based on cost constraints."""

    def optimize_selection(
        self,
        query: SearchQuery,
        providers: Dict[str, SearchProvider],
        scores: Dict[str, float],
        budget: float,
    ) -> List[str]:
        """
        Select providers while considering budget constraints.

        Args:
            query: The search query
            providers: Available providers
            scores: Provider scores for this query
            budget: Maximum budget to spend

        Returns:
            List of selected provider names
        """
        # Calculate costs and value ratios
        costs = {}
        value_ratios = {}

        for name, provider in providers.items():
            cost = provider.estimate_cost(query)
            costs[name] = cost
            value_ratios[name] = scores[name] / cost if cost > 0 else float("inf")

        # Sort providers by value ratio
        ranked_providers = sorted(
            value_ratios.items(), key=lambda x: x[1], reverse=True
        )

        # Select providers within budget
        selected = []
        remaining_budget = budget

        for name, _ in ranked_providers:
            cost = costs[name]
            if cost <= remaining_budget:
                selected.append(name)
                remaining_budget -= cost

                # Stop if we've selected enough providers
                if len(selected) >= 2:
                    break

        # Return at least one provider, even if it exceeds budget
        if not selected and ranked_providers:
            selected = [ranked_providers[0][0]]

        return selected
