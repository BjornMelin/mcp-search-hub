"""Cascade routing implementation with fallback support for resilient provider execution."""

import asyncio
import time
from contextlib import asynccontextmanager

from ..models.query import QueryFeatures, SearchQuery
from ..models.router import (
    CascadeExecutionPolicy,
    ProviderExecutionResult,
    TimeoutConfig,
)
from ..providers.base import SearchProvider
from ..utils.logging import get_logger

logger = get_logger(__name__)


class CascadeRouter:
    """
    Advanced cascade router implementing multiple fallback strategies:
    - Sequential cascade routing with automatic failover
    - Circuit breaker integration for provider protection
    - Dynamic timeout adjustment based on query complexity
    - Hybrid routing for multi-provider queries
    """

    def __init__(
        self,
        providers: dict[str, SearchProvider],
        timeout_config: TimeoutConfig,
        execution_policy: CascadeExecutionPolicy,
    ):
        self.providers = providers
        self.timeout_config = timeout_config
        self.execution_policy = execution_policy
        self._execution_stats = {}
        self._circuit_breakers = {}
        self._init_circuit_breakers()

    def _init_circuit_breakers(self):
        """Initialize circuit breakers for each provider."""
        for provider_name in self.providers:
            self._circuit_breakers[provider_name] = CircuitBreaker(
                max_failures=self.execution_policy.circuit_breaker_max_failures,
                reset_timeout=self.execution_policy.circuit_breaker_reset_timeout,
            )

    async def execute_cascade(
        self,
        query: SearchQuery,
        features: QueryFeatures,
        selected_providers: list[str],
    ) -> dict[str, ProviderExecutionResult]:
        """
        Execute providers in cascade mode with automatic failover.

        Returns:
            Dict mapping provider names to their execution results
        """
        results = {}
        execution_order = self._determine_execution_order(selected_providers, features)

        # Apply dynamic timeout based on query complexity
        dynamic_timeout = self._calculate_dynamic_timeout(features)

        # Log execution plan
        logger.info(
            f"Cascade execution plan: {execution_order} with timeout {dynamic_timeout}s"
        )

        # First, mark any providers that were filtered out by circuit breakers
        for provider_name in selected_providers:
            if provider_name not in execution_order:
                # Provider was filtered out by circuit breaker
                results[provider_name] = ProviderExecutionResult(
                    provider_name=provider_name,
                    success=False,
                    error="Circuit breaker open",
                    duration_ms=0,
                    skipped=True,
                )

        for provider_name in execution_order:
            # Execute provider with timeout and error handling
            result = await self._execute_provider(
                provider_name=provider_name,
                query=query,
                timeout=dynamic_timeout,
                is_primary=(provider_name == execution_order[0]),
            )

            results[provider_name] = result

            # Update circuit breaker state
            if result.success:
                self._circuit_breakers[provider_name].record_success()
            else:
                self._circuit_breakers[provider_name].record_failure()

            # Stop cascade if primary succeeded (unless hybrid mode)
            if result.success and not self.execution_policy.cascade_on_success:
                break

            # Stop cascade if we've met minimum success requirement
            successful_count = sum(1 for r in results.values() if r.success)
            if successful_count >= self.execution_policy.min_successful_providers:
                break

        return results

    async def _execute_provider(
        self,
        provider_name: str,
        query: SearchQuery,
        timeout: float,
        is_primary: bool,
    ) -> ProviderExecutionResult:
        """Execute a single provider with timeout and error handling."""
        provider = self.providers[provider_name]
        start_time = time.time()

        try:
            # Add backoff delay for secondary providers
            if not is_primary and self.execution_policy.secondary_delay_ms > 0:
                await asyncio.sleep(self.execution_policy.secondary_delay_ms / 1000)

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

    def _determine_execution_order(
        self,
        selected_providers: list[str],
        features: QueryFeatures,
    ) -> list[str]:
        """
        Determine provider execution order based on:
        - Circuit breaker states
        - Provider health metrics
        - Query features
        - Historical performance
        """
        # Filter out providers with open circuit breakers
        available_providers = [
            p for p in selected_providers if not self._circuit_breakers[p].is_open
        ]

        if not available_providers:
            # If all circuits are open, try the selected providers anyway
            logger.warning("All circuit breakers open, attempting original order")
            return selected_providers

        # TODO: Sort by performance metrics and query affinity
        # For now, return the filtered list
        return available_providers

    def _calculate_dynamic_timeout(self, features: QueryFeatures) -> float:
        """Calculate dynamic timeout based on query complexity."""
        base_timeout = self.timeout_config.base_timeout_ms / 1000

        # Adjust timeout based on complexity
        complexity_factor = 1.0 + (features.complexity * 0.5)

        # Adjust for question queries (typically need more processing)
        if features.contains_question:
            complexity_factor *= 1.2

        # Adjust for time-sensitive queries (need faster response)
        if features.time_sensitivity > 0.7:
            complexity_factor *= 0.8

        # Apply limits
        dynamic_timeout = base_timeout * complexity_factor
        return max(
            self.timeout_config.min_timeout_ms / 1000,
            min(dynamic_timeout, self.timeout_config.max_timeout_ms / 1000),
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


class CircuitBreaker:
    """Simple circuit breaker implementation for provider protection."""

    def __init__(self, max_failures: int = 3, reset_timeout: float = 30.0):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.state = "closed"  # closed, open, half-open

    @property
    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self.state == "closed":
            return False

        # Check if timeout has passed
        if (
            self.last_failure_time
            and time.time() - self.last_failure_time > self.reset_timeout
        ):
            self.state = "half-open"
            self.failure_count = 0

        return self.state == "open"

    def record_success(self):
        """Record successful execution."""
        if self.state == "half-open":
            self.state = "closed"
        self.failure_count = 0

    def record_failure(self):
        """Record failed execution."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.max_failures:
            self.state = "open"
