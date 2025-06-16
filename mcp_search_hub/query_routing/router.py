"""Modern router implementation following 2025 best practices."""

import asyncio
import logging
import random
import time
from collections import deque
from typing import Any

from circuitbreaker import circuit

from ..models.base import HealthStatus
from ..models.query import QueryFeatures, SearchQuery
from ..models.results import SearchResponse
from ..providers.base import SearchProvider

logger = logging.getLogger(__name__)


class ProviderMetrics:
    """Track simple metrics for provider selection."""

    def __init__(self, window_size: int = 10):
        self.response_times: deque[float] = deque(maxlen=window_size)
        self.success_count: int = 0
        self.error_count: int = 0
        self.last_success: float | None = None

    @property
    def avg_response_time(self) -> float:
        """Average response time from recent requests."""
        if not self.response_times:
            return float("inf")
        return sum(self.response_times) / len(self.response_times)

    @property
    def success_rate(self) -> float:
        """Success rate based on all requests."""
        total = self.success_count + self.error_count
        return self.success_count / total if total > 0 else 1.0

    @property
    def is_healthy(self) -> bool:
        """Simple health check based on recent performance."""
        # Consider healthy if success rate > 50% and had recent success
        if self.success_rate < 0.5:
            return False

        # If we've had successes, check if recent (within 5 minutes)
        if self.last_success is not None:
            return (time.time() - self.last_success) < 300

        return True

    def record_success(self, response_time: float) -> None:
        """Record a successful request."""
        self.response_times.append(response_time)
        self.success_count += 1
        self.last_success = time.time()

    def record_error(self) -> None:
        """Record a failed request."""
        self.error_count += 1


class SearchRouter:
    """
    Modern router for multi-provider search aggregation.

    Features:
    - Circuit breaker pattern for resilience
    - Metrics tracking for provider selection
    - Concurrent execution with semaphore-based limiting
    - Provider selection algorithms
    - Graceful error handling
    """

    def __init__(
        self,
        providers: dict[str, SearchProvider],
        max_concurrent: int = 3,
        default_timeout: float = 30.0,
        circuit_failure_threshold: int = 5,
        circuit_recovery_timeout: float = 30.0,
    ):
        self.providers = providers
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout

        # Track metrics for each provider
        self.metrics: dict[str, ProviderMetrics] = {
            name: ProviderMetrics() for name in providers
        }

        # Circuit breaker settings
        self.circuit_failure_threshold = circuit_failure_threshold
        self.circuit_recovery_timeout = circuit_recovery_timeout

        # Create semaphore for concurrency limiting
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def route_and_execute(
        self,
        query: SearchQuery,
        features: QueryFeatures,
        max_providers: int = 3,
        selection_strategy: str = "best_performance",
    ) -> dict[str, Any]:
        """
        Route query to providers and execute search.

        Args:
            query: Search query to execute
            features: Query features for provider selection
            max_providers: Maximum number of providers to use
            selection_strategy: Provider selection strategy

        Returns:
            Dictionary mapping provider names to their results
        """
        # Select providers based on strategy
        selected_providers = self._select_providers(
            query, features, max_providers, selection_strategy
        )

        if not selected_providers:
            logger.warning("No healthy providers available")
            return {}

        logger.info(f"Selected providers: {selected_providers}")

        # Execute searches concurrently
        tasks = {}
        for provider_name in selected_providers:
            provider = self.providers[provider_name]
            task = asyncio.create_task(
                self._execute_with_circuit_breaker(provider_name, provider, query)
            )
            tasks[provider_name] = task

        # Wait for completion with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks.values(), return_exceptions=True),
                timeout=self.default_timeout,
            )
        except TimeoutError:
            logger.warning("Router timeout, cancelling remaining tasks")
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            results = [None] * len(tasks)

        # Process results
        final_results = {}
        for provider_name, result in zip(tasks.keys(), results, strict=True):
            if isinstance(result, SearchResponse):
                final_results[provider_name] = result.results
            elif isinstance(result, Exception):
                logger.error(f"Provider {provider_name} failed: {result}")
            # Ignore None results (timeouts or cancellations)

        return final_results

    def _select_providers(
        self,
        query: SearchQuery,
        features: QueryFeatures,
        max_providers: int,
        strategy: str,
    ) -> list[str]:
        """Select providers based on strategy."""
        # Filter to healthy providers
        healthy_providers = [
            name
            for name, provider in self.providers.items()
            if provider.enabled and self.metrics[name].is_healthy
        ]

        if not healthy_providers:
            # If no healthy providers, try all enabled ones
            healthy_providers = [
                name for name, provider in self.providers.items() if provider.enabled
            ]

        if not healthy_providers:
            return []

        # Apply selection strategy
        if strategy == "best_performance":
            # Sort by performance (response time + success rate)
            healthy_providers.sort(
                key=lambda name: (
                    self.metrics[name].avg_response_time
                    / max(0.1, self.metrics[name].success_rate)
                )
            )
        elif strategy == "power_of_two":
            # Power of two random selection for load balancing
            if len(healthy_providers) >= 2:
                candidates = random.sample(
                    healthy_providers, min(2, len(healthy_providers))
                )
                healthy_providers = sorted(
                    candidates, key=lambda name: self.metrics[name].avg_response_time
                )
        elif strategy == "round_robin":
            # Simple round robin (random for now, could track state)
            random.shuffle(healthy_providers)
        # else: use providers as-is (all enabled)

        return healthy_providers[:max_providers]

    async def _execute_with_circuit_breaker(
        self, provider_name: str, provider: SearchProvider, query: SearchQuery
    ) -> SearchResponse | None:
        """Execute provider search with circuit breaker protection."""

        @circuit(
            failure_threshold=self.circuit_failure_threshold,
            recovery_timeout=self.circuit_recovery_timeout,
            expected_exception=(Exception,),
        )
        async def protected_search():
            async with self.semaphore:  # Limit concurrency
                start_time = time.time()
                try:
                    result = await provider.search(query)

                    # Record success
                    response_time = time.time() - start_time
                    self.metrics[provider_name].record_success(response_time)

                    return result

                except Exception as e:
                    # Record error
                    self.metrics[provider_name].record_error()
                    logger.error(f"Provider {provider_name} error: {e}")
                    raise

        try:
            return await protected_search()
        except Exception as e:
            # Circuit breaker is open or provider failed
            logger.warning(f"Provider {provider_name} unavailable: {e}")
            return None

    def get_provider_health(self) -> dict[str, dict[str, Any]]:
        """Get health status for all providers."""
        health_status = {}

        for name, provider in self.providers.items():
            metrics = self.metrics[name]
            health_status[name] = {
                "enabled": provider.enabled,
                "healthy": metrics.is_healthy,
                "success_rate": metrics.success_rate,
                "avg_response_time": metrics.avg_response_time,
                "total_requests": metrics.success_count + metrics.error_count,
                "last_success": metrics.last_success,
            }

        return health_status

    async def check_health(self) -> tuple[HealthStatus, str]:
        """Check overall router health."""
        enabled_providers = [p for p in self.providers.values() if p.enabled]
        if not enabled_providers:
            return HealthStatus.UNHEALTHY, "No providers enabled"

        healthy_count = sum(
            1
            for name in self.providers
            if self.providers[name].enabled and self.metrics[name].is_healthy
        )

        if healthy_count == 0:
            return HealthStatus.UNHEALTHY, "No healthy providers"
        if healthy_count < len(enabled_providers) / 2:
            return (
                HealthStatus.DEGRADED,
                f"Only {healthy_count}/{len(enabled_providers)} providers healthy",
            )
        return (
            HealthStatus.HEALTHY,
            f"{healthy_count}/{len(enabled_providers)} providers healthy",
        )

    def get_metrics(self) -> dict[str, Any]:
        """Get router metrics."""
        return {
            "providers": {
                name: {
                    "success_rate": metrics.success_rate,
                    "avg_response_time": metrics.avg_response_time,
                    "total_requests": metrics.success_count + metrics.error_count,
                    "is_healthy": metrics.is_healthy,
                }
                for name, metrics in self.metrics.items()
            },
            "total_providers": len(self.providers),
            "enabled_providers": sum(1 for p in self.providers.values() if p.enabled),
            "healthy_providers": sum(
                1
                for name in self.providers
                if self.providers[name].enabled and self.metrics[name].is_healthy
            ),
        }
