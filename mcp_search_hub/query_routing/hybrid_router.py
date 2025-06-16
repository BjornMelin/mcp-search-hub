"""Three-tier hybrid routing implementation.

This module implements a clean three-tier routing architecture that balances
simplicity with advanced capabilities. It routes 80% of queries through fast
deterministic rules while reserving LLM routing for complex queries.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field

from ..config.settings import AppSettings
from ..models.query import SearchQuery
from ..models.results import SearchResponse
from ..providers.base import SearchProvider
from .complexity_classifier import ComplexityClassifier
from .llm_router import LLMQueryRouter
from .pattern_router import PatternRouter
from .simple_keyword_router import SimpleKeywordRouter

logger = logging.getLogger(__name__)


class RoutingDecision(BaseModel):
    """Result of routing decision."""

    providers: list[str] = Field(..., description="Selected provider names")
    strategy: str = Field(default="parallel", description="Execution strategy")
    complexity_level: str = Field(..., description="Query complexity level")
    confidence: float = Field(..., description="Confidence in routing decision")
    explanation: str = Field(..., description="Explanation of routing logic")


class HybridRouter:
    """Three-tier hybrid routing system.

    This router implements a clean, maintainable architecture that routes
    queries through three tiers based on complexity:
    - Tier 1 (80%): Simple keyword routing (<1ms)
    - Tier 2 (15%): Pattern-based routing (<10ms)
    - Tier 3 (5%): LLM-enhanced routing (200-500ms)
    """

    def __init__(
        self,
        providers: dict[str, SearchProvider],
        settings: AppSettings | None = None,
    ):
        """Initialize the hybrid router.

        Args:
            providers: Available search providers
            settings: Application settings
        """
        self.providers = providers
        self.settings = settings or AppSettings()

        # Initialize routing components
        self.complexity_classifier = ComplexityClassifier()
        self.tier1_router = SimpleKeywordRouter(providers)
        self.tier2_router = PatternRouter(providers)
        self.tier3_router = None

        # Initialize LLM router if enabled
        if self.settings.llm_routing_enabled:
            self.tier3_router = LLMQueryRouter(fallback_scorer=self.tier2_router)

        # Metrics for monitoring
        self.metrics = {
            "tier1_count": 0,
            "tier2_count": 0,
            "tier3_count": 0,
            "total_queries": 0,
            "avg_routing_time_ms": 0.0,
        }

        logger.info(
            f"Initialized HybridRouter with {len(providers)} providers, "
            f"LLM routing: {'enabled' if self.settings.llm_routing_enabled else 'disabled'}"
        )

    async def route(self, query: SearchQuery) -> RoutingDecision:
        """Route query to appropriate providers using three-tier system.

        Args:
            query: The search query to route

        Returns:
            RoutingDecision with selected providers and strategy
        """
        import time

        start_time = time.time()

        # Classify query complexity
        complexity = self.complexity_classifier.classify(query)
        self.metrics["total_queries"] += 1

        # Route based on complexity tier
        if complexity.score < 0.3:
            # Tier 1: Simple keyword routing
            self.metrics["tier1_count"] += 1
            providers = await self.tier1_router.route(query)
            decision = RoutingDecision(
                providers=providers,
                strategy="parallel",
                complexity_level="simple",
                confidence=0.9,
                explanation=f"Simple query routed via keywords. {complexity.explanation}",
            )

        elif complexity.score < 0.7:
            # Tier 2: Pattern-based routing
            self.metrics["tier2_count"] += 1
            providers = await self.tier2_router.route(query)
            decision = RoutingDecision(
                providers=providers,
                strategy="parallel",
                complexity_level="medium",
                confidence=0.8,
                explanation=f"Medium complexity routed via patterns. {complexity.explanation}",
            )

        # Tier 3: LLM routing (if enabled)
        elif self.tier3_router and self.settings.llm_routing_enabled:
            self.metrics["tier3_count"] += 1
            providers = await self._route_with_llm(query)
            strategy = "cascade" if len(providers) > 2 else "parallel"
            decision = RoutingDecision(
                providers=providers,
                strategy=strategy,
                complexity_level="complex",
                confidence=0.85,
                explanation=f"Complex query routed via LLM. {complexity.explanation}",
            )
        else:
            # Fallback to Tier 2 if LLM disabled
            self.metrics["tier2_count"] += 1
            providers = await self.tier2_router.route(query)
            decision = RoutingDecision(
                providers=providers,
                strategy="parallel",
                complexity_level="complex",
                confidence=0.7,
                explanation=f"Complex query routed via patterns (LLM disabled). {complexity.explanation}",
            )

        # Update routing time metrics
        elapsed_ms = (time.time() - start_time) * 1000
        self._update_avg_routing_time(elapsed_ms)

        logger.debug(
            f"Routed query (complexity: {complexity.level}, score: {complexity.score:.2f}) "
            f"to {len(decision.providers)} providers in {elapsed_ms:.1f}ms"
        )

        return decision

    async def execute(
        self,
        query: SearchQuery,
        decision: RoutingDecision,
    ) -> dict[str, SearchResponse]:
        """Execute search across selected providers.

        Args:
            query: The search query
            decision: Routing decision with providers and strategy

        Returns:
            Dictionary of provider results
        """
        if decision.strategy == "cascade":
            return await self._execute_cascade(query, decision.providers)
        return await self._execute_parallel(query, decision.providers)

    async def _execute_parallel(
        self,
        query: SearchQuery,
        provider_names: list[str],
    ) -> dict[str, SearchResponse]:
        """Execute searches in parallel across providers.

        Args:
            query: The search query
            provider_names: List of provider names to search

        Returns:
            Dictionary of provider results
        """
        tasks = []
        for name in provider_names:
            if name in self.providers:
                provider = self.providers[name]
                tasks.append(self._search_with_provider(name, provider, query))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        provider_results = {}
        for name, result in zip(provider_names, results, strict=False):
            if isinstance(result, Exception):
                logger.error(f"Provider {name} failed: {result}")
            else:
                provider_results[name] = result

        return provider_results

    async def _execute_cascade(
        self,
        query: SearchQuery,
        provider_names: list[str],
    ) -> dict[str, SearchResponse]:
        """Execute searches in cascade (sequential with early stopping).

        Args:
            query: The search query
            provider_names: Ordered list of provider names

        Returns:
            Dictionary of provider results
        """
        provider_results = {}
        total_results = 0
        target_results = query.max_results

        for name in provider_names:
            if name not in self.providers:
                continue

            # Check if we have enough results
            if total_results >= target_results:
                break

            # Search with this provider
            try:
                provider = self.providers[name]
                result = await self._search_with_provider(name, provider, query)
                provider_results[name] = result
                total_results += len(result.results)
            except Exception as e:
                logger.error(f"Provider {name} failed in cascade: {e}")

        return provider_results

    async def _search_with_provider(
        self,
        name: str,
        provider: SearchProvider,
        query: SearchQuery,
    ) -> SearchResponse:
        """Execute search with a single provider.

        Args:
            name: Provider name
            provider: Provider instance
            query: Search query

        Returns:
            Search response from provider
        """
        try:
            # Apply timeout from settings
            timeout = getattr(self.settings, f"{name}_timeout", 10000) / 1000.0
            return await asyncio.wait_for(provider.search(query), timeout=timeout)
        except TimeoutError:
            logger.error(f"Provider {name} timed out")
            return SearchResponse(
                results=[], query=query.query, total_results=0, provider=name
            )
        except Exception as e:
            logger.error(f"Provider {name} error: {e}")
            return SearchResponse(
                results=[], query=query.query, total_results=0, provider=name
            )

    async def _route_with_llm(self, query: SearchQuery) -> list[str]:
        """Route query using LLM router.

        Args:
            query: The search query

        Returns:
            List of selected provider names
        """
        # Get features for LLM routing
        from ..query_routing.analyzer import QueryAnalyzer

        analyzer = QueryAnalyzer()
        features = analyzer.extract_features(query)

        # Score each provider
        provider_scores = []
        for name, provider in self.providers.items():
            score = await self.tier3_router.score_provider(name, provider, features)
            provider_scores.append((name, score.weighted_score))

        # Sort by score and select top providers
        provider_scores.sort(key=lambda x: x[1], reverse=True)

        # Select providers with score > 0.5 or top 3
        selected = []
        for name, score in provider_scores:
            if score > 0.5 or len(selected) < 3:
                selected.append(name)
            if len(selected) >= 5:  # Max 5 providers
                break

        return selected

    def _update_avg_routing_time(self, elapsed_ms: float) -> None:
        """Update average routing time metric."""
        prev_avg = self.metrics["avg_routing_time_ms"]
        count = self.metrics["total_queries"]
        self.metrics["avg_routing_time_ms"] = (
            prev_avg * (count - 1) + elapsed_ms
        ) / count

    def get_metrics(self) -> dict[str, Any]:
        """Get router metrics for monitoring."""
        metrics = dict(self.metrics)

        # Calculate tier percentages
        total = metrics["total_queries"]
        if total > 0:
            metrics["tier1_percentage"] = (metrics["tier1_count"] / total) * 100
            metrics["tier2_percentage"] = (metrics["tier2_count"] / total) * 100
            metrics["tier3_percentage"] = (metrics["tier3_count"] / total) * 100

        return metrics
