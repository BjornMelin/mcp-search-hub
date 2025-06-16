"""Protocol definitions for component interfaces.

This module defines the core interface protocols that all components should implement
for consistent behavior across the search hub. These protocols use Python's typing.Protocol
for structural subtyping, allowing for flexible implementation while enforcing
consistent interfaces.
"""

from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import (
    Any,
    Protocol,
    TypeVar,
    runtime_checkable,
)

from ..config.settings import ComponentConfig
from .base import HealthStatus
from .query import SearchQuery
from .results import SearchResponse, SearchResult

# Type variables for generic protocols
T = TypeVar("T")
ConfigT = TypeVar("ConfigT", bound="ComponentConfig")
ResultT = TypeVar("ResultT")
MetricsT = TypeVar("MetricsT", bound=dict[str, Any])


@runtime_checkable
class ServiceLifecycle(Protocol):
    """Core lifecycle protocol that all service components should implement."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the component, setting up required resources."""
        ...

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up resources used by the component."""
        ...

    @abstractmethod
    async def reset(self) -> None:
        """Reset the component to its initial state."""
        ...


@runtime_checkable
class HealthCheck(Protocol):
    """Health checking protocol for components."""

    @abstractmethod
    async def check_health(self) -> tuple[HealthStatus, str]:
        """
        Check the health status of the component.

        Returns:
            A tuple of (status, message) where status is one of
            HealthStatus.HEALTHY, HealthStatus.DEGRADED, or HealthStatus.UNHEALTHY
        """
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        """
        Check if the component is in a healthy state.

        Returns:
            True if the component is healthy, False otherwise
        """
        ...


@runtime_checkable
class ConfigurableComponent(Protocol[ConfigT]):
    """Protocol for components that can be configured."""

    @abstractmethod
    def configure(self, config: ConfigT) -> None:
        """
        Configure the component with the provided configuration.

        Args:
            config: Configuration object for this component
        """
        ...

    @abstractmethod
    def get_config(self) -> ConfigT:
        """
        Get the current configuration of the component.

        Returns:
            The current configuration
        """
        ...


@runtime_checkable
class MetricsProvider(Protocol[MetricsT]):
    """Protocol for components that provide metrics."""

    @abstractmethod
    def get_metrics(self) -> MetricsT:
        """
        Get metrics for this component.

        Returns:
            A dictionary containing metrics
        """
        ...

    @abstractmethod
    def reset_metrics(self) -> None:
        """Reset all metrics to their initial values."""
        ...


@runtime_checkable
class AsyncExecutable(Protocol[T]):
    """Protocol for components that can be executed asynchronously."""

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> T:
        """
        Execute the component's primary function.

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            The result of execution
        """
        ...

    @abstractmethod
    async def execute_with_timeout(
        self, timeout_ms: int, *args: Any, **kwargs: Any
    ) -> T:
        """
        Execute with a specific timeout.

        Args:
            timeout_ms: Timeout in milliseconds
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            The result of execution

        Raises:
            TimeoutError: If execution exceeds the timeout
        """
        ...

    @abstractmethod
    def cancel(self) -> bool:
        """
        Cancel an ongoing execution.

        Returns:
            True if cancellation was successful, False otherwise
        """
        ...


@runtime_checkable
class ErrorBoundary(Protocol):
    """Protocol for components with standardized error handling."""

    @abstractmethod
    def handle_error(self, error: Exception) -> tuple[bool, str]:
        """
        Handle an error that occurred during component operation.

        Args:
            error: The exception that occurred

        Returns:
            Tuple of (should_retry, error_message)
        """
        ...

    @abstractmethod
    def is_error_retryable(self, error: Exception) -> bool:
        """
        Determine if an error can be retried.

        Args:
            error: The exception to check

        Returns:
            True if the error can be retried, False otherwise
        """
        ...


# Provider-specific interfaces


@runtime_checkable
class SearchProviderProtocol(
    ServiceLifecycle,
    HealthCheck,
    ConfigurableComponent,
    MetricsProvider,
    Protocol,
):
    """Protocol defining the interface for search providers."""

    name: str

    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResponse:
        """
        Execute a search and return results.

        Args:
            query: The search query to execute

        Returns:
            A SearchResponse containing results and metadata
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        """
        Return provider capabilities.

        Returns:
            A dictionary of capability information
        """
        ...

    @abstractmethod
    def estimate_cost(self, query: SearchQuery) -> float:
        """
        Estimate the cost of executing the query.

        Args:
            query: The query to estimate cost for

        Returns:
            Estimated cost in arbitrary units (usually USD)
        """
        ...

    @abstractmethod
    async def check_status(self) -> tuple[HealthStatus, str]:
        """
        Check the status of the provider.

        Returns:
            A tuple of (status, message) where status is one of
            HealthStatus.HEALTHY, HealthStatus.DEGRADED, or HealthStatus.UNHEALTHY
        """
        ...


# Router-specific interfaces


@runtime_checkable
class ExecutionStrategyProtocol(Protocol):
    """Protocol for execution strategies in the router."""

    @abstractmethod
    async def execute(
        self,
        query: SearchQuery,
        providers: dict[str, SearchProviderProtocol],
        selected_providers: list[str],
        timeout_ms: int,
    ) -> dict[str, Any]:
        """
        Execute providers according to the strategy.

        Args:
            query: The search query to execute
            providers: Dictionary of available providers
            selected_providers: List of provider names to use
            timeout_ms: Timeout in milliseconds

        Returns:
            Dictionary of execution results
        """
        ...


@runtime_checkable
class ProviderScorerProtocol(Protocol):
    """Protocol for provider scoring systems."""

    @abstractmethod
    def score_provider(
        self,
        provider_name: str,
        provider: SearchProviderProtocol,
        query: SearchQuery,
    ) -> float:
        """
        Score a provider for a given query.

        Args:
            provider_name: The name of the provider
            provider: The provider instance
            query: The search query

        Returns:
            A score (higher is better)
        """
        ...


@runtime_checkable
class RouterProtocol(
    ServiceLifecycle,
    HealthCheck,
    ConfigurableComponent,
    MetricsProvider,
    Protocol,
):
    """Protocol for query routers."""

    @abstractmethod
    async def route(
        self,
        query: SearchQuery,
        providers: dict[str, SearchProviderProtocol],
    ) -> list[str]:
        """
        Route a query to appropriate providers.

        Args:
            query: The search query
            providers: Available providers

        Returns:
            List of provider names to use
        """
        ...

    @abstractmethod
    async def route_and_execute(
        self,
        query: SearchQuery,
        providers: dict[str, SearchProviderProtocol],
    ) -> dict[str, Any]:
        """
        Route query to providers and execute.

        Args:
            query: The search query
            providers: Available providers

        Returns:
            Results from execution
        """
        ...


# Result processing interfaces


@runtime_checkable
class ResultProcessorProtocol(Protocol):
    """Protocol for result processors."""

    @abstractmethod
    def process_results(
        self,
        results: list[SearchResult],
    ) -> list[SearchResult]:
        """
        Process search results.

        Args:
            results: List of search results to process

        Returns:
            Processed search results
        """
        ...


@runtime_checkable
class ResultMergerProtocol(
    ServiceLifecycle,
    ConfigurableComponent,
    Protocol,
):
    """Protocol for result mergers."""

    @abstractmethod
    def merge_results(
        self,
        provider_results: dict[str, SearchResponse],
        max_results: int = 10,
    ) -> list[SearchResult]:
        """
        Merge results from multiple providers into a unified ranked list.

        Args:
            provider_results: Dictionary mapping provider names to their responses
            max_results: Maximum number of results to return

        Returns:
            A merged and ranked list of results
        """
        ...


@runtime_checkable
class StreamingResultProcessor(Protocol):
    """Protocol for streaming result processors."""

    @abstractmethod
    async def process_stream(
        self,
        result_stream: AsyncIterator[SearchResult],
    ) -> AsyncIterator[SearchResult]:
        """
        Process a stream of search results.

        Args:
            result_stream: Async iterator of search results

        Returns:
            Processed async iterator of search results
        """
        ...
