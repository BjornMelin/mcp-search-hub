"""Unified router combining parallel and cascade execution strategies."""

import asyncio
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any

from ..models.base import HealthStatus
from ..models.component import RouterBase
from ..models.config import RouterConfig
from ..models.interfaces import (
    ExecutionStrategyProtocol,
    ProviderScorerProtocol,
    SearchProviderProtocol,
)
from ..models.query import QueryFeatures, SearchQuery
from ..models.results import SearchResponse
from ..models.router import (
    CascadeExecutionPolicy,
    ProviderExecutionResult,
    ProviderPerformanceMetrics,
    ProviderScore,
    RoutingDecision,
    ScoringMode,
    TimeoutConfig,
)
from ..utils.logging import get_logger
from .circuit_breaker import CircuitBreaker
from .cost_optimizer import CostOptimizer
from .scoring_calculator import ScoringCalculator

logger = get_logger(__name__)


class ExecutionStrategy(ABC, ExecutionStrategyProtocol):
    """Abstract base class for provider execution strategies."""

    @abstractmethod
    async def execute(
        self,
        query: SearchQuery,
        features: QueryFeatures,
        providers: dict[str, SearchProviderProtocol],
        selected_providers: list[str],
        timeout_config: TimeoutConfig,
    ) -> dict[str, ProviderExecutionResult]:
        """Execute providers according to the strategy."""


class ProviderScorer(ProviderScorerProtocol):
    """Protocol for provider scoring systems."""

    def score_provider(
        self,
        provider_name: str,
        provider: SearchProviderProtocol,
        features: QueryFeatures,
        metrics: ProviderPerformanceMetrics | None = None,
    ) -> ProviderScore:
        """Score a provider for given query features."""


class UnifiedRouter(RouterBase[RouterConfig]):
    """
    Unified router that combines parallel and cascade routing with pluggable strategies.

    This router consolidates the functionality of QueryRouter and CascadeRouter into
    a single, extensible system with pluggable execution strategies and scoring systems.
    """

    def __init__(
        self,
        name: str = "unified_router",
        providers: dict[str, SearchProviderProtocol] | None = None,
        config: RouterConfig | None = None,
        performance_metrics: dict[str, ProviderPerformanceMetrics] | None = None,
    ):
        """Initialize the unified router."""
        # If no config is provided, create a default one
        if config is None:
            config = RouterConfig(name=name)

        super().__init__(name, config)

        # Set up provider mapping
        self.providers = providers or {}

        # Set timeout config from router config
        self.timeout_config = TimeoutConfig(
            base_timeout_ms=config.base_timeout_ms,
            min_timeout_ms=config.min_timeout_ms,
            max_timeout_ms=config.max_timeout_ms,
            complexity_factor=0.5,  # Default complexity factor
        )

        self.performance_metrics = performance_metrics or {}

        # Core components
        self.cost_optimizer = CostOptimizer()
        self.scoring_calculator = ScoringCalculator()

        # Import here to avoid circular imports
        from .llm_router import LLM_ROUTER_ENABLED, LLMQueryRouter

        # Initialize LLM router if enabled
        self.llm_router = None
        if LLM_ROUTER_ENABLED:
            try:
                self.llm_router = LLMQueryRouter(
                    fallback_scorer=self.scoring_calculator
                )
                logger.info("LLM query routing enabled")
            except Exception as e:
                logger.error(f"Failed to initialize LLM router: {e}")

        # Execution strategies
        self._strategies: dict[str, ExecutionStrategy] = {
            "parallel": ParallelExecutionStrategy(),
            "cascade": CascadeExecutionStrategy(),
        }

        # Default scorers
        self._scorers: list[ProviderScorer] = [self.scoring_calculator]
        # Add LLM router as a scorer if available
        if self.llm_router:
            self._scorers.append(self.llm_router)

        # Circuit breakers for each provider
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

        # Router metrics
        self.metrics = {
            "total_queries": 0,
            "queries_per_provider": {},
            "avg_providers_per_query": 0.0,
            "success_rate": 1.0,
            "error_count": 0,
            "avg_routing_time_ms": 0.0,
            "provider_selection_counts": {},
        }

        self.initialized = False

    async def initialize(self) -> None:
        """Initialize the router and its components."""
        await super().initialize()
        self._init_circuit_breakers()
        self.initialized = True

    def _init_circuit_breakers(self) -> None:
        """Initialize circuit breakers for each provider."""
        for provider_name in self.providers:
            self._circuit_breakers[provider_name] = CircuitBreaker(
                max_failures=3,
                reset_timeout=30.0,  # Default values
            )

    async def route(
        self,
        query: SearchQuery,
        providers: dict[str, SearchProviderProtocol] | None = None,
    ) -> list[str]:
        """
        Route a query to appropriate providers.

        Args:
            query: The search query
            providers: Available providers (uses instance providers if None)

        Returns:
            List of provider names to use
        """
        # Use instance providers if none provided
        providers_to_use = providers or self.providers

        # Extract features from query
        from .analyzer import QueryAnalyzer

        analyzer = QueryAnalyzer()
        features = analyzer.extract_features(query)

        # Select providers based on scoring
        routing_decision = self.select_providers(query, features)

        # If explicit providers were specified, filter the selection
        if query.providers:
            # Filter but keep order from scoring
            filtered_providers = [
                p for p in routing_decision.selected_providers if p in query.providers
            ]
            # Add any missing providers that were explicitly requested
            for p in query.providers:
                if p not in filtered_providers and p in providers_to_use:
                    filtered_providers.append(p)

            selected_providers = filtered_providers
            logger.info(f"Using explicitly requested providers: {selected_providers}")
        else:
            selected_providers = routing_decision.selected_providers

        return selected_providers

    async def route_and_execute(
        self,
        query: SearchQuery,
        providers: dict[str, SearchProviderProtocol] | None = None,
        budget: float | None = None,
        strategy: str | None = None,
    ) -> dict[str, ProviderExecutionResult]:
        """
        Route query to providers and execute with selected strategy.

        Args:
            query: The search query
            providers: Dictionary of available providers (uses instance providers if None)
            budget: Optional budget constraint
            strategy: Execution strategy ("parallel" or "cascade", auto-selected if None)

        Returns:
            Dict mapping provider names to execution results
        """
        start_time = time.time()
        providers_to_use = providers or self.providers

        # Extract features from query
        from .analyzer import QueryAnalyzer

        analyzer = QueryAnalyzer()
        features = analyzer.extract_features(query)

        try:
            # Process routing hints if provided
            if query.routing_hints:
                logger.info(f"Processing routing hints: {query.routing_hints}")
                from .llm_router import RoutingHintParser

                hint_parser = RoutingHintParser()
                hint_params = hint_parser.parse_hints(query.routing_hints)

                # Apply hints for provider selection if no explicit providers specified
                if not query.providers and "preferred_providers" in hint_params:
                    query.providers = hint_params["preferred_providers"]
                    logger.info(
                        f"Using preferred providers from hints: {query.providers}"
                    )

                # Apply strategy hint if no explicit strategy specified
                if strategy is None and "strategy" in hint_params:
                    strategy = hint_params["strategy"]
                    logger.info(f"Using strategy from hints: {strategy}")

            # Use routing_strategy from query if provided
            if strategy is None and query.routing_strategy:
                strategy = query.routing_strategy

            # Use explicitly provided budget if available
            if budget is None and query.budget is not None:
                budget = query.budget

            # Select providers based on scoring
            routing_decision = self.select_providers(query, features, budget)

            # If explicit providers were specified, filter the selection
            if query.providers:
                # Filter but keep order from scoring
                filtered_providers = [
                    p
                    for p in routing_decision.selected_providers
                    if p in query.providers
                ]
                # Add any missing providers that were explicitly requested
                for p in query.providers:
                    if p not in filtered_providers and p in providers_to_use:
                        filtered_providers.append(p)

                selected_providers = filtered_providers
                logger.info(
                    f"Using explicitly requested providers: {selected_providers}"
                )
            else:
                selected_providers = routing_decision.selected_providers

            # Determine execution strategy if not specified
            if strategy is None:
                strategy = self._determine_strategy(query, features, selected_providers)

            logger.info(
                f"Routing to {len(selected_providers)} providers using {strategy} strategy"
            )

            # Get and execute the strategy
            exec_strategy = self._strategies.get(strategy)
            if not exec_strategy:
                logger.warning(f"Unknown strategy {strategy}, using parallel")
                exec_strategy = self._strategies["parallel"]

            # Execute providers according to strategy
            results = await exec_strategy.execute(
                query=query,
                features=features,
                providers=providers_to_use,
                selected_providers=selected_providers,
                timeout_config=self.timeout_config,
            )

            # Update circuit breakers based on results
            self._update_circuit_breakers(results)

            # Update metrics
            self._update_metrics(selected_providers, results, time.time() - start_time)

            return results

        except Exception as e:
            # Update error metrics
            self.metrics["error_count"] += 1
            logger.error(f"Router execution failed: {str(e)}")
            raise

    def _update_metrics(
        self,
        selected_providers: list[str],
        results: dict[str, ProviderExecutionResult],
        duration: float,
    ) -> None:
        """Update router metrics."""
        self.metrics["total_queries"] += 1

        # Update provider selection counts
        for provider in selected_providers:
            if provider not in self.metrics["provider_selection_counts"]:
                self.metrics["provider_selection_counts"][provider] = 0
            self.metrics["provider_selection_counts"][provider] += 1

        # Update queries per provider
        for provider_name, result in results.items():
            if provider_name not in self.metrics["queries_per_provider"]:
                self.metrics["queries_per_provider"][provider_name] = 0
            self.metrics["queries_per_provider"][provider_name] += 1

        # Update average providers per query
        total_providers_used = len(self.metrics["provider_selection_counts"])
        self.metrics["avg_providers_per_query"] = sum(
            self.metrics["provider_selection_counts"].values()
        ) / max(1, self.metrics["total_queries"])

        # Update success rate
        success_count = sum(1 for r in results.values() if r.success)
        if selected_providers:
            query_success_rate = success_count / len(selected_providers)
            # Update with moving average
            prev_rate = self.metrics["success_rate"]
            prev_count = self.metrics["total_queries"] - 1
            self.metrics["success_rate"] = (
                prev_rate * prev_count + query_success_rate
            ) / self.metrics["total_queries"]

        # Update avg routing time with moving average
        prev_avg = self.metrics["avg_routing_time_ms"]
        prev_count = self.metrics["total_queries"] - 1
        self.metrics["avg_routing_time_ms"] = (
            prev_avg * prev_count + duration * 1000
        ) / self.metrics["total_queries"]

    def select_providers(
        self,
        query: SearchQuery,
        features: QueryFeatures,
        budget: float | None = None,
        mode: ScoringMode = ScoringMode.AVG,
    ) -> RoutingDecision:
        """Select the best provider(s) for a query using enhanced scoring."""
        provider_scores = []

        # Score each provider using all configured scorers
        for name, provider in self.providers.items():
            # Skip providers with open circuit breakers
            if self._circuit_breakers[name].is_open:
                logger.info(f"Skipping provider {name} due to open circuit breaker")
                continue

            # Calculate composite score from all scorers
            score = self._calculate_composite_score(name, provider, features)
            provider_scores.append(score)

        # Sort by weighted score
        provider_scores.sort(key=lambda x: x.weighted_score, reverse=True)

        # Select providers based on budget or score threshold
        if budget is not None:
            selected_providers = self._select_with_budget(
                query, provider_scores, budget
            )
        else:
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
            query_id=query.query,
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

    def _calculate_composite_score(
        self,
        provider_name: str,
        provider: SearchProviderProtocol,
        features: QueryFeatures,
    ) -> ProviderScore:
        """Calculate composite score from all registered scorers."""
        metrics = self.performance_metrics.get(provider_name)

        # For now, just use the scoring calculator
        # In the future, we can average scores from multiple scorers
        return self.scoring_calculator.calculate_provider_score(
            provider_name, provider, features, metrics
        )

    def _determine_strategy(
        self,
        query: SearchQuery,
        features: QueryFeatures,
        providers: list[str],
    ) -> str:
        """Automatically determine the best execution strategy."""
        # Use cascade for:
        # 1. Single provider queries (for reliability)
        if len(providers) == 1:
            return "cascade"

        # 2. High-importance/complexity queries
        if features.complexity > 0.7:
            return "cascade"

        # 3. Queries explicitly requesting high reliability
        if query.advanced and query.advanced.get("use_cascade", False):
            return "cascade"

        # 4. Queries with web content extraction (often need fallbacks)
        if features.content_type == "web_content":
            return "cascade"

        # Default to parallel execution
        return "parallel"

    def _update_circuit_breakers(
        self, results: dict[str, ProviderExecutionResult]
    ) -> None:
        """Update circuit breaker states based on execution results."""
        for provider_name, result in results.items():
            circuit_breaker = self._circuit_breakers.get(provider_name)
            if circuit_breaker:
                if result.success:
                    circuit_breaker.record_success()
                else:
                    circuit_breaker.record_failure()

    def _select_with_budget(
        self,
        query: SearchQuery,
        provider_scores: list[ProviderScore],
        budget: float,
    ) -> list[str]:
        """Select providers considering budget constraints."""
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

            # Limit to max_providers (from config)
            if len(selected) >= self.config.max_providers:
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
            separation_confidence = min(score_gap / 0.5, 1.0)
            confidences.append(separation_confidence)

        # 3. Consistency among selected providers
        if len(selected_scores) > 1:
            score_variance = self._calculate_variance(
                [s.weighted_score for s in selected_scores]
            )
            consistency_confidence = 1.0 - min(score_variance / 0.1, 1.0)
            confidences.append(consistency_confidence)

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

    def add_strategy(self, name: str, strategy: ExecutionStrategy) -> None:
        """Add a custom execution strategy."""
        self._strategies[name] = strategy

    def add_scorer(self, scorer: ProviderScorer) -> None:
        """Add a custom provider scorer."""
        self._scorers.append(scorer)

    def update_performance_metrics(
        self, provider_name: str, metrics: ProviderPerformanceMetrics
    ) -> None:
        """Update performance metrics for a provider."""
        self.performance_metrics[provider_name] = metrics

    def get_provider_ranking(self, features: QueryFeatures) -> list[ProviderScore]:
        """Get ranking of all providers for given query features."""
        scores = []

        for name, provider in self.providers.items():
            score = self._calculate_composite_score(name, provider, features)
            scores.append(score)

        scores.sort(key=lambda x: x.weighted_score, reverse=True)
        return scores

    def get_metrics(self) -> dict[str, Any]:
        """Get current router metrics."""
        # Add some derived metrics
        self.metrics["provider_count"] = len(self.providers)
        self.metrics["enabled_providers"] = sum(
            1 for p in self.providers.values() if getattr(p, "enabled", True)
        )
        self.metrics["circuit_breaker_status"] = {
            name: {"open": cb.is_open, "failure_count": cb.failure_count}
            for name, cb in self._circuit_breakers.items()
        }

        return self.metrics

    def reset_metrics(self) -> None:
        """Reset router metrics."""
        self.metrics = {
            "total_queries": 0,
            "queries_per_provider": {},
            "avg_providers_per_query": 0.0,
            "success_rate": 1.0,
            "error_count": 0,
            "avg_routing_time_ms": 0.0,
            "provider_selection_counts": {},
        }

    async def check_health(self) -> tuple[HealthStatus, str]:
        """Check health of the router."""
        if not self.initialized:
            return HealthStatus.UNHEALTHY, "Router not initialized"

        # Check circuit breakers status
        open_circuits = sum(1 for cb in self._circuit_breakers.values() if cb.is_open)
        total_circuits = len(self._circuit_breakers)

        if open_circuits == total_circuits and total_circuits > 0:
            return (
                HealthStatus.UNHEALTHY,
                f"All circuit breakers open ({open_circuits}/{total_circuits})",
            )
        if open_circuits > 0:
            return (
                HealthStatus.DEGRADED,
                f"Some circuit breakers open ({open_circuits}/{total_circuits})",
            )

        return HealthStatus.HEALTHY, "Router is healthy"

    async def _do_execute(
        self, *args: Any, **kwargs: Any
    ) -> dict[str, ProviderExecutionResult]:
        """Execute the router with the given arguments."""
        # Extract query from args or kwargs
        query = None
        if args and isinstance(args[0], SearchQuery):
            query = args[0]
        elif "query" in kwargs and isinstance(kwargs["query"], SearchQuery):
            query = kwargs["query"]
        else:
            raise ValueError("No SearchQuery provided to execute")

        # Extract other parameters
        providers = kwargs.get("providers", self.providers)
        budget = kwargs.get("budget")
        strategy = kwargs.get("strategy")

        # Execute routing
        return await self.route_and_execute(query, providers, budget, strategy)


class ParallelExecutionStrategy(ExecutionStrategy):
    """Execute all selected providers in parallel."""

    async def execute(
        self,
        query: SearchQuery,
        features: QueryFeatures,
        providers: dict[str, SearchProviderProtocol],
        selected_providers: list[str],
        timeout_config: TimeoutConfig,
    ) -> dict[str, ProviderExecutionResult]:
        """Execute all providers in parallel."""
        provider_tasks = {}
        results = {}
        start_time = time.time()

        # Create tasks for all selected providers
        for provider_name in selected_providers:
            if provider_name in providers:
                provider = providers[provider_name]
                provider_tasks[provider_name] = asyncio.create_task(
                    self._execute_provider(provider_name, provider, query)
                )

        # Calculate dynamic timeout
        timeout = self._calculate_timeout(features, timeout_config)

        # Wait for all searches to complete with timeout
        done, pending = await asyncio.wait(provider_tasks.values(), timeout=timeout)

        # Cancel any pending tasks
        for task in pending:
            task.cancel()

        # Collect results
        for provider_name, task in provider_tasks.items():
            if task in done and not task.exception():
                response = task.result()
                results[provider_name] = ProviderExecutionResult(
                    provider_name=provider_name,
                    success=True,
                    response=response,
                    duration_ms=(time.time() - start_time) * 1000,
                )
            else:
                # Handle errors or timeouts
                error_msg = "Timeout"
                if task in done and task.exception():
                    error_msg = str(task.exception())

                results[provider_name] = ProviderExecutionResult(
                    provider_name=provider_name,
                    success=False,
                    error=error_msg,
                    duration_ms=timeout * 1000,
                )

        return results

    async def _execute_provider(
        self, provider_name: str, provider: SearchProviderProtocol, query: SearchQuery
    ) -> SearchResponse:
        """Execute a single provider."""
        return await provider.search(query)

    def _calculate_timeout(
        self, features: QueryFeatures, timeout_config: TimeoutConfig
    ) -> float:
        """Calculate dynamic timeout for parallel execution."""
        base_timeout = timeout_config.base_timeout_ms / 1000
        complexity_factor = 1.0 + (
            features.complexity * timeout_config.complexity_factor
        )

        # Apply time sensitivity adjustment
        if features.time_sensitivity > 0.7:
            complexity_factor *= 0.8

        dynamic_timeout = base_timeout * complexity_factor
        return max(
            timeout_config.min_timeout_ms / 1000,
            min(dynamic_timeout, timeout_config.max_timeout_ms / 1000),
        )


class CascadeExecutionStrategy(ExecutionStrategy):
    """Execute providers in cascade with fallback support."""

    def __init__(self, policy: CascadeExecutionPolicy | None = None):
        """Initialize cascade strategy with optional policy."""
        self.policy = policy or CascadeExecutionPolicy()

    async def execute(
        self,
        query: SearchQuery,
        features: QueryFeatures,
        providers: dict[str, SearchProviderProtocol],
        selected_providers: list[str],
        timeout_config: TimeoutConfig,
    ) -> dict[str, ProviderExecutionResult]:
        """Execute providers in cascade mode."""
        results = {}
        execution_order = selected_providers  # Can be customized based on performance

        # Calculate dynamic timeout
        dynamic_timeout = self._calculate_dynamic_timeout(features, timeout_config)

        logger.info(
            f"Cascade execution plan: {execution_order} with timeout {dynamic_timeout}s"
        )

        for i, provider_name in enumerate(execution_order):
            is_primary = i == 0
            provider = providers.get(provider_name)
            if not provider:
                continue

            # Execute provider with timeout and error handling
            result = await self._execute_provider(
                provider_name=provider_name,
                provider=provider,
                query=query,
                timeout=dynamic_timeout,
                is_primary=is_primary,
            )

            results[provider_name] = result

            # Stop cascade if primary succeeded (unless policy says otherwise)
            if result.success and not self.policy.cascade_on_success:
                break

            # Stop cascade if we've met minimum success requirement
            successful_count = sum(1 for r in results.values() if r.success)
            if successful_count >= self.policy.min_successful_providers:
                break

        return results

    async def _execute_provider(
        self,
        provider_name: str,
        provider: SearchProviderProtocol,
        query: SearchQuery,
        timeout: float,
        is_primary: bool,
    ) -> ProviderExecutionResult:
        """Execute a single provider with timeout and error handling."""
        start_time = time.time()

        try:
            # Add backoff delay for secondary providers
            if not is_primary and self.policy.secondary_delay_ms > 0:
                await asyncio.sleep(self.policy.secondary_delay_ms / 1000)

            # Execute with timeout
            async with self._timeout_context(timeout):
                response = await provider.search(query)

            duration_ms = (time.time() - start_time) * 1000

            # Validate response
            if not response or not hasattr(response, "results"):
                raise ValueError("Invalid response format")

            return ProviderExecutionResult(
                provider_name=provider_name,
                success=True,
                response=response,
                duration_ms=duration_ms,
                is_primary=is_primary,
            )

        except TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Provider {provider_name} timed out after {timeout}s")

            return ProviderExecutionResult(
                provider_name=provider_name,
                success=False,
                error="Timeout",
                duration_ms=duration_ms,
                is_primary=is_primary,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Provider {provider_name} error: {str(e)}")

            return ProviderExecutionResult(
                provider_name=provider_name,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
                is_primary=is_primary,
            )

    @asynccontextmanager
    async def _timeout_context(self, timeout: float):
        """Context manager for timeout handling."""
        try:
            # Using Python 3.11+ native timeout
            async with asyncio.timeout(timeout):
                yield
        except AttributeError:
            # Fallback for older Python versions
            try:
                async with asyncio.timeout_at(
                    asyncio.get_event_loop().time() + timeout
                ):
                    yield
            except AttributeError:
                # Ultimate fallback
                task = asyncio.current_task()
                handle = asyncio.get_event_loop().call_later(
                    timeout, lambda: task.cancel()
                )
                try:
                    yield
                finally:
                    handle.cancel()

    def _calculate_dynamic_timeout(
        self, features: QueryFeatures, timeout_config: TimeoutConfig
    ) -> float:
        """Calculate dynamic timeout based on query complexity."""
        base_timeout = timeout_config.base_timeout_ms / 1000

        # Adjust timeout based on complexity
        complexity_factor = 1.0 + (
            features.complexity * timeout_config.complexity_factor
        )

        # Adjust for question queries (typically need more processing)
        if features.contains_question:
            complexity_factor *= 1.2

        # Adjust for time-sensitive queries (need faster response)
        if features.time_sensitivity > 0.7:
            complexity_factor *= 0.8

        # Apply limits
        dynamic_timeout = base_timeout * complexity_factor
        return max(
            timeout_config.min_timeout_ms / 1000,
            min(dynamic_timeout, timeout_config.max_timeout_ms / 1000),
        )
