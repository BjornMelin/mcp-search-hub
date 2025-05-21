# Consistent Service Interfaces

MCP Search Hub implements a consistent set of interfaces across all component types to ensure uniformity, predictability, and maintainability. This document describes the standardized interface architecture.

## Core Interface Protocols

All components implement a consistent set of base interfaces that provide common functionality:

### Service Lifecycle

The `ServiceLifecycle` protocol defines methods for managing a component's lifecycle:

```python
@runtime_checkable
class ServiceLifecycle(Protocol):
    """Core lifecycle protocol that all service components should implement."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the component, setting up required resources."""

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up resources used by the component."""

    @abstractmethod
    async def reset(self) -> None:
        """Reset the component to its initial state."""
```

### Health Checking

The `HealthCheck` protocol enables all components to report their operational status:

```python
@runtime_checkable
class HealthCheck(Protocol):
    """Health checking protocol for components."""

    @abstractmethod
    async def check_health(self) -> Tuple[HealthStatus, str]:
        """
        Check the health status of the component.

        Returns:
            A tuple of (status, message) where status is one of
            HealthStatus.HEALTHY, HealthStatus.DEGRADED, or HealthStatus.UNHEALTHY
        """

    @abstractmethod
    def is_healthy(self) -> bool:
        """
        Check if the component is in a healthy state.

        Returns:
            True if the component is healthy, False otherwise
        """
```

### Configuration

The `ConfigurableComponent` protocol standardizes configuration management:

```python
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

    @abstractmethod
    def get_config(self) -> ConfigT:
        """
        Get the current configuration of the component.

        Returns:
            The current configuration
        """
```

### Metrics

The `MetricsProvider` protocol ensures consistent metrics collection:

```python
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

    @abstractmethod
    def reset_metrics(self) -> None:
        """Reset all metrics to their initial values."""
```

### Execution

The `AsyncExecutable` protocol standardizes asynchronous operation execution:

```python
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

    @abstractmethod
    async def execute_with_timeout(self, timeout_ms: int, *args: Any, **kwargs: Any) -> T:
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

    @abstractmethod
    def cancel(self) -> bool:
        """
        Cancel an ongoing execution.

        Returns:
            True if cancellation was successful, False otherwise
        """
```

### Error Handling

The `ErrorBoundary` protocol provides consistent error handling:

```python
@runtime_checkable
class ErrorBoundary(Protocol):
    """Protocol for components with standardized error handling."""

    @abstractmethod
    def handle_error(self, error: Exception) -> Tuple[bool, str]:
        """
        Handle an error that occurred during component operation.

        Args:
            error: The exception that occurred

        Returns:
            Tuple of (should_retry, error_message)
        """

    @abstractmethod
    def is_error_retryable(self, error: Exception) -> bool:
        """
        Determine if an error can be retried.

        Args:
            error: The exception to check

        Returns:
            True if the error can be retried, False otherwise
        """
```

## Component-Specific Interfaces

In addition to the core interfaces, each component type implements domain-specific interfaces:

### Provider Interfaces

Search providers implement the `SearchProviderProtocol` which combines the core interfaces with provider-specific methods:

```python
@runtime_checkable
class SearchProviderProtocol(ServiceLifecycle, HealthCheck, ConfigurableComponent, MetricsProvider, Protocol):
    """Protocol defining the interface for search providers."""

    name: str

    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search and return results."""

    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """Return provider capabilities."""

    @abstractmethod
    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""

    @abstractmethod
    async def check_status(self) -> Tuple[HealthStatus, str]:
        """Check the status of the provider."""
```

### Router Interfaces

Query routers implement the `RouterProtocol` which combines the core interfaces with router-specific methods:

```python
@runtime_checkable
class RouterProtocol(ServiceLifecycle, HealthCheck, ConfigurableComponent, MetricsProvider, Protocol):
    """Protocol for query routers."""

    @abstractmethod
    async def route(self, query: SearchQuery, providers: Dict[str, SearchProviderProtocol]) -> List[str]:
        """Route a query to appropriate providers."""

    @abstractmethod
    async def route_and_execute(self, query: SearchQuery, providers: Dict[str, SearchProviderProtocol]) -> Dict[str, Any]:
        """Route query to providers and execute."""
```

### Result Processing Interfaces

Result processors implement the `ResultProcessorProtocol` and result mergers implement the `ResultMergerProtocol`:

```python
@runtime_checkable
class ResultProcessorProtocol(Protocol):
    """Protocol for result processors."""

    @abstractmethod
    def process_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """Process search results."""
```

```python
@runtime_checkable
class ResultMergerProtocol(ServiceLifecycle, ConfigurableComponent, Protocol):
    """Protocol for result mergers."""

    @abstractmethod
    def merge_results(
        self,
        provider_results: Dict[str, SearchResponse],
        max_results: int = 10,
    ) -> List[SearchResult]:
        """Merge results from multiple providers into a unified ranked list."""
```

## Base Implementation Classes

To reduce duplication and ensure consistency, MCP Search Hub provides base implementation classes for each interface:

- `Component`: Base implementation of `ServiceLifecycle` and `HealthCheck`
- `ConfigurableComponentBase`: Base implementation of `ConfigurableComponent`
- `MetricsProviderBase`: Base implementation of `MetricsProvider`
- `AsyncExecutableBase`: Base implementation of `AsyncExecutable`
- `ErrorBoundaryBase`: Base implementation of `ErrorBoundary`
- `CompleteComponentBase`: Combines all of the above in a single convenient base class

Plus domain-specific base classes:

- `SearchProviderBase`: Base implementation for search providers
- `RouterBase`: Base implementation for query routers
- `ResultProcessorBase`: Base implementation for result processors
- `ResultMergerBase`: Base implementation for result mergers

## Benefits of Consistent Interfaces

1. **Standardization**: All components follow the same patterns and conventions
2. **Composability**: Components with consistent interfaces can be easily combined
3. **Testing**: Standardized interfaces simplify testing with mocks and stubs
4. **Extensibility**: New components can be added by implementing the appropriate interfaces
5. **Tooling**: Consistent interfaces enable generic tools for monitoring, configuration, etc.
6. **Documentation**: Standardized interfaces make documentation more consistent and easier to understand

## Using the Interfaces

When implementing a new component:

1. Identify the appropriate interface protocol(s) for your component type
2. Extend the corresponding base implementation class
3. Implement the required methods
4. Follow the established patterns for configuration, metrics, and error handling

Example:

```python
class MyCustomProvider(SearchProviderBase[ProviderConfig]):
    """Custom search provider implementation."""
    
    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search and return results."""
        # Implementation here
        
    def get_capabilities(self) -> Dict[str, Any]:
        """Return provider capabilities."""
        # Implementation here
        
    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Implementation here
```

## Interface Evolution

The interface protocols are designed to evolve gracefully:

1. **Non-breaking additions**: New methods can be added with default implementations
2. **Method signature evolution**: Type parameters can be made more generic, return types more specific
3. **Interface extension**: New interfaces can extend existing ones without breaking changes

When changing interfaces, careful consideration is given to backward compatibility, ensuring that existing component implementations continue to work with minimal or no changes.