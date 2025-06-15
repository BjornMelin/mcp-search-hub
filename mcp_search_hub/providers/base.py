"""Base class for all search providers.

This module defines the foundational interfaces and base classes for all search
providers in the MCP Search Hub. It provides consistent patterns for provider
initialization, configuration, health monitoring, and result handling.

The module includes:
- ProviderConfig: Base configuration schema for all providers
- ProviderMetrics: Standardized metrics collection
- SearchProvider: Abstract base class with common functionality

Example:
    Creating a new provider:
        >>> class MyProvider(SearchProvider):
        ...     async def search_impl(self, query: SearchQuery) -> SearchResponse:
        ...         # Implementation here
        ...         pass
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, cast

from ..config.settings import ComponentConfig
from ..models.base import HealthStatus
from ..models.component import SearchProviderBase
from ..models.query import SearchQuery
from ..models.results import SearchResponse
from ..utils.logging import get_logger

logger = get_logger(__name__)


class ProviderConfig(ComponentConfig):
    """Base configuration for search providers."""

    api_key: str | None = None
    enabled: bool = True
    timeout_ms: int = 30000
    max_retries: int = 3
    rate_limit_per_minute: int | None = None
    rate_limit_per_hour: int | None = None
    rate_limit_per_day: int | None = None


class ProviderMetrics(dict[str, Any]):
    """Metrics for search providers."""

    def __init__(self):
        """Initialize provider metrics."""
        super().__init__(
            {
                "total_queries": 0,
                "successful_queries": 0,
                "failed_queries": 0,
                "avg_response_time_ms": 0.0,
                "total_results": 0,
                "avg_results_per_query": 0.0,
                "estimated_cost": 0.0,
                "error_rate": 0.0,
                "last_query_time": None,
            }
        )


class SearchProvider(SearchProviderBase[ProviderConfig], ABC):
    """Base class for all search providers."""

    def __init__(self, name: str, config: ProviderConfig | None = None):
        """Initialize the search provider with name and optional config."""
        super().__init__(name, config)
        self.metrics = ProviderMetrics()
        self.last_query_time = 0.0
        self.query_count = 0
        self.success_count = 0
        self.error_count = 0
        self.total_cost = 0.0

    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search and return results."""
        ...

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        """Return provider capabilities."""
        ...

    @abstractmethod
    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        ...

    async def check_status(self) -> tuple[HealthStatus, str]:
        """
        Check the status of the provider.

        Returns:
            A tuple of (status, message) where status is one of
            HealthStatus.HEALTHY, HealthStatus.DEGRADED, or HealthStatus.UNHEALTHY
        """
        try:
            # Default implementation: try to make a minimal API call
            # to check if the service is responsive
            # Providers can override this with more specific checks

            # Make a minimal query to check if the provider is responsive
            test_query = SearchQuery(query="test", max_results=1)
            response = await self.search(test_query)

            if response.error:
                return (
                    HealthStatus.DEGRADED,
                    f"Provider returning errors: {response.error}",
                )
            return HealthStatus.HEALTHY, "Provider is operational"

        except Exception as e:
            return HealthStatus.UNHEALTHY, f"Provider check failed: {str(e)}"

    async def _do_execute(self, *args: Any, **kwargs: Any) -> SearchResponse:
        """Execute the search operation with metrics tracking."""
        start_time = time.time()
        self.query_count += 1
        self.last_query_time = start_time

        try:
            # Extract the query from args or kwargs
            query = None
            if args and isinstance(args[0], SearchQuery):
                query = args[0]
            elif "query" in kwargs and isinstance(kwargs["query"], SearchQuery):
                query = kwargs["query"]
            else:
                raise ValueError("No SearchQuery provided to execute")

            # Perform the search
            response = await self.search(query)

            # Update metrics on success
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000

            self.success_count += 1
            self.metrics["total_queries"] += 1
            self.metrics["successful_queries"] += 1

            # Update average response time with running average
            prev_avg = self.metrics["avg_response_time_ms"]
            prev_count = self.metrics["successful_queries"] - 1  # Exclude current
            new_avg = (prev_avg * prev_count + duration_ms) / max(
                1, self.metrics["successful_queries"]
            )
            self.metrics["avg_response_time_ms"] = new_avg

            # Update cost metrics
            cost = self.estimate_cost(query)
            self.total_cost += cost
            self.metrics["estimated_cost"] = self.total_cost

            # Update result counts if we have results
            if response and response.results:
                self.metrics["total_results"] += len(response.results)
                self.metrics["avg_results_per_query"] = self.metrics[
                    "total_results"
                ] / max(1, self.metrics["successful_queries"])

            # Update last query time and error rate
            self.metrics["last_query_time"] = end_time
            self.metrics["error_rate"] = self.error_count / max(1, self.query_count)

            return response

        except Exception as e:
            # Update metrics on error
            end_time = time.time()
            self.error_count += 1
            self.metrics["failed_queries"] += 1
            self.metrics["error_rate"] = self.error_count / max(1, self.query_count)

            # Log error and re-raise
            logger.error(f"Provider {self.name} search error: {str(e)}")
            raise

    def reset_metrics(self) -> None:
        """Reset all metrics to initial values."""
        self.metrics = ProviderMetrics()
        self.last_query_time = 0.0
        self.query_count = 0
        self.success_count = 0
        self.error_count = 0
        self.total_cost = 0.0

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics."""
        # Ensure metrics are up to date
        self.metrics["error_rate"] = self.error_count / max(1, self.query_count)
        return cast(dict[str, Any], self.metrics)

    async def initialize(self) -> None:
        """Initialize the provider, setting up required resources."""
        await super().initialize()
        logger.info(f"Initializing provider: {self.name}")
        self.reset_metrics()

    async def cleanup(self) -> None:
        """Clean up resources used by the provider."""
        await super().cleanup()
        logger.info(f"Cleaning up provider: {self.name}")
