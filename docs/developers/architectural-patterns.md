# Consistent Architectural Patterns

This document outlines the unified architectural patterns to be applied consistently across all modules in the MCP Search Hub. These patterns ensure code quality, maintainability, and consistent behavior throughout the codebase.

## Core Architectural Principles

### 1. Protocol-Based Interface Design

All components implement Protocol interfaces defined in `models/interfaces.py`:

- Use `typing.Protocol` with `@runtime_checkable` for structural subtyping
- Prefer composition of small, focused protocols over large interfaces
- Implement common behavior through abstract base classes (`models/component.py`)
- Use generic types with TypeVar for type-safe implementations

### 2. Component Lifecycle Management

All components follow a consistent lifecycle pattern:

- **Initialization**: Async `initialize()` method for resource setup
- **Cleanup**: Async `cleanup()` method for resource release
- **Reset**: Async `reset()` method for returning to initial state
- **Health Checking**: `check_health()` for component health status

### 3. Configuration Management

Components use a standardized approach to configuration:

- Configuration classes inherit from Pydantic's `BaseModel`
- Configuration hierarchy follows component hierarchy
- All configurable parameters defined in Pydantic models
- Environment variables used for overrides with sensible defaults
- Components accept config in constructor with reasonable defaults

### 4. Error Handling

Consistent error handling patterns across all components:

- Hierarchical exception types in `utils/errors.py`
- Error classification (retryable vs. non-retryable)
- Standardized error response format
- Error boundaries with explicit handling
- Comprehensive error logging with context preservation

### 5. Metrics Collection

Uniform metrics tracking across all component types:

- Standard metrics structure for each component type
- Metrics updated during operation through standard interfaces
- Reset capability through `reset_metrics()`
- Performance tracking with consistent timing approach
- Moving averages for statistical metrics

### 6. Composition over Inheritance

Prefer component composition over deep inheritance hierarchies:

- Components explicitly declare dependencies
- Constructor dependency injection pattern
- Component containers provide required dependencies
- Service locator pattern avoided in favor of direct injection

### 7. Async/Await Consistency

Consistent async patterns across the codebase:

- All blocking operations use async/await
- Resource management uses `__aenter__`/`__aexit__` protocols
- Timeout handling with consistent approach
- Use of asyncio primitives for coordination

## Implementation Requirements

### 1. Provider Implementation Pattern

All provider implementations follow this pattern:

```python
class ExampleProvider(SearchProviderBase[ProviderConfig]):
    """Provider for Example search API."""
    
    def __init__(
        self,
        name: str = "example",
        config: Optional[ProviderConfig] = None,
    ):
        """Initialize with optional configuration."""
        super().__init__(name, config)
        # Provider-specific setup
    
    async def initialize(self) -> None:
        """Initialize provider resources."""
        await super().initialize()
        # Provider-specific initialization
    
    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute search."""
        # Delegate to _do_execute for async execution pattern
        return await self.execute(query)
    
    async def _do_execute(self, query: SearchQuery) -> SearchResponse:
        """Implement search execution."""
        # Provider-specific search implementation
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Return provider capabilities."""
        return {
            "name": self.name,
            "features": [...],
            # Other capability information
        }
    
    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate query cost."""
        # Cost estimation logic
        
    async def cleanup(self) -> None:
        """Release provider resources."""
        # Provider-specific cleanup
        await super().cleanup()
```

### 2. Router Implementation Pattern

All router implementations follow this pattern:

```python
class ExampleRouter(RouterBase[RouterConfig]):
    """Router implementation with consistent patterns."""
    
    def __init__(
        self,
        name: str = "example_router",
        config: Optional[RouterConfig] = None,
        providers: Optional[Dict[str, SearchProviderProtocol]] = None,
    ):
        """Initialize router with dependencies."""
        super().__init__(name, config)
        self.providers = providers or {}
        self.analyzer = QueryAnalyzer()  # Injected dependency
    
    async def route(
        self,
        query: SearchQuery,
        providers: Optional[Dict[str, SearchProviderProtocol]] = None,
    ) -> List[str]:
        """Route query to providers."""
        providers = providers or self.providers
        # Routing implementation
        
    async def route_and_execute(
        self,
        query: SearchQuery,
        providers: Optional[Dict[str, SearchProviderProtocol]] = None,
    ) -> Dict[str, Any]:
        """Route and execute query."""
        return await self.execute(query, providers or self.providers)
    
    async def _do_execute(
        self,
        query: SearchQuery,
        providers: Dict[str, SearchProviderProtocol],
    ) -> Dict[str, Any]:
        """Implement execution logic."""
        # Execute providers based on routing decision
```

### 3. Result Processor Implementation Pattern

All result processors follow this pattern:

```python
class ExampleProcessor(ResultProcessorBase[ProcessorConfig]):
    """Result processor with consistent patterns."""
    
    def __init__(
        self,
        name: str = "example_processor",
        config: Optional[ProcessorConfig] = None,
    ):
        """Initialize processor."""
        super().__init__(name, config)
        # Processor-specific setup
    
    def process_results(
        self,
        results: List[SearchResult],
    ) -> List[SearchResult]:
        """Process search results."""
        # Delegate to execute pattern
        return self.execute(results)
    
    async def _do_execute(
        self,
        results: List[SearchResult],
    ) -> List[SearchResult]:
        """Implement processing logic."""
        # Processing implementation
```

### 4. Middleware Implementation Pattern

All middleware follows this pattern:

```python
class ExampleMiddleware(BaseMiddleware):
    """Middleware with consistent patterns."""
    
    def _initialize(self, **options):
        """Initialize with middleware-specific options."""
        # Extract options with defaults
        self.order = options.get("order", 10)
        # Other middleware-specific initialization
    
    async def process_request(self, request, context):
        """Process incoming request."""
        # Request processing logic
        return await self.next_middleware.process_request(request, context)
    
    async def process_response(self, response, context):
        """Process outgoing response."""
        # Response processing logic
        return await self.next_middleware.process_response(response, context)
```

## Areas Requiring Pattern Standardization

Based on the analysis of the existing codebase, the following areas need consistent pattern application:

### 1. Provider Module Standardization

- **Retry Logic**: Move retry functionality into `BaseMCPProvider` or use a decorator pattern to ensure consistent retry behavior across all providers.

- **Error Handling**: Ensure all providers map specific API errors to consistent error types with proper inheritance from base error classes.

- **Provider-Specific Logic**: Move provider-specific logic from `GenericMCPProvider` into a more configuration-driven approach, keeping implementation consistent.

### 2. Query Routing Standardization

- **Component Initialization**: Convert ad-hoc component creation to constructor injection for `QueryAnalyzer` and other dependencies.

- **Configuration Management**: Replace hardcoded values in `ScoringCalculator` and `CostOptimizer` with configurable Pydantic models.

- **Execution Strategies**: Standardize the implementation of execution strategies to follow the established Protocol pattern.

### 3. Result Processing Standardization

- **Interface Consistency**: Standardize on a single pattern for component interfaces (either Class-based or Function-based, but not both).

- **Error Handling**: Implement consistent error handling across result processing components.

- **Metrics Collection**: Use standardized metrics collection patterns in all result processors.

### 4. Middleware Standardization

- **Error Handling**: Standardize error handling patterns across middleware components.

- **Context Management**: Create a standard pattern for context state management across middleware.

- **Configuration Management**: Ensure middleware components use consistent configuration approaches.

## Best Practices to Apply Consistently

### 1. Dependency Injection

- Inject dependencies through constructors rather than importing them in methods
- Make dependencies explicit in interfaces
- Use Optional types with sensible defaults for optional dependencies

### 2. Configuration Management

- Use Pydantic models for all configurations
- Validate configurations at initialization time
- Provide sensible defaults
- Support environment variable overrides
- Document all configuration options

### 3. Error Handling

- Categorize errors as retryable or non-retryable
- Use specific exception types from the hierarchy
- Include context in error messages
- Preserve stack traces
- Log errors at appropriate levels

### 4. Testing Support

- Design components for testability
- Make dependencies injectable for mocking
- Add health check mechanisms for integration testing
- Separate interface from implementation for easier testing

### 5. Documentation

- Document component interfaces and responsibilities
- Include examples of correct usage
- Document configuration options and error handling
- Include architectural decisions and rationales

## Implementation Checklist

To apply these patterns consistently, the following changes should be implemented:

- [ ] Update provider components to follow consistent patterns
  - [ ] Standardize retry logic across providers
  - [ ] Ensure consistent error mapping
  - [ ] Move provider-specific logic to configuration

- [ ] Refactor query routing components
  - [ ] Update router to use constructor injection
  - [ ] Convert hardcoded configurations to Pydantic models
  - [ ] Standardize execution strategy implementations

- [ ] Align result processing components
  - [ ] Standardize result processor interfaces
  - [ ] Implement consistent error handling
  - [ ] Update metrics collection

- [ ] Standardize middleware components
  - [ ] Normalize error handling patterns
  - [ ] Create consistent context management pattern
  - [ ] Align configuration approaches

- [ ] Apply comprehensive documentation
  - [ ] Document all components and interfaces
  - [ ] Include usage examples
  - [ ] Update architecture documentation

## Migration Strategy

To minimize disruption while applying these patterns:

1. Start with base classes and interfaces, ensuring they reflect the desired patterns
2. Update concrete implementations incrementally, starting with most critical components
3. Add comprehensive tests to verify pattern compliance
4. Update documentation to reflect the standardized patterns
5. Conduct code reviews focused on pattern compliance