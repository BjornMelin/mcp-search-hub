# Migration Guide: Unified Router System

This document outlines the migration from the separate QueryRouter and CascadeRouter to the new UnifiedRouter system.

## Overview

The UnifiedRouter consolidates the functionality of QueryRouter and CascadeRouter into a single, extensible system with:
- Pluggable execution strategies (parallel, cascade, custom)
- Pluggable provider scoring systems
- Centralized timeout management
- Unified circuit breaker integration

## Key Changes

### 1. Router Consolidation

**Before:**
```python
# Two separate routers
self.router = QueryRouter(self.providers)
self.cascade_router = CascadeRouter(
    providers=self.providers,
    timeout_config=timeout_config,
    execution_policy=cascade_policy,
)
```

**After:**
```python
# Single unified router
self.router = UnifiedRouter(
    providers=self.providers,
    timeout_config=timeout_config,
)
```

### 2. Execution Strategy Selection

**Before:**
```python
# Manual strategy selection in search logic
if self._should_use_cascade(query, features, providers_to_use):
    execution_results = await self.cascade_router.execute_cascade(...)
else:
    # Parallel execution code
```

**After:**
```python
# Automatic strategy selection or explicit override
execution_results = await self.router.route_and_execute(
    query=query,
    features=features,
    strategy=None,  # Auto-select based on query
)
```

### 3. Provider Selection and Execution

**Before:**
```python
# Separate selection and execution
routing_decision = self.router.select_providers(query, features, budget)
providers_to_use = routing_decision.selected_providers

# Then execute separately based on strategy
if use_cascade:
    results = await self.cascade_router.execute_cascade(...)
else:
    # Parallel execution
```

**After:**
```python
# Combined selection and execution
execution_results = await self.router.route_and_execute(
    query=query,
    features=features,
    budget=budget,
    strategy=strategy,  # Optional
)
```

## Architecture Benefits

### 1. Extensibility

The new system supports adding custom strategies and scorers:

```python
# Add custom execution strategy
class CustomStrategy(ExecutionStrategy):
    async def execute(self, ...):
        # Custom logic
        pass

router.add_strategy("custom", CustomStrategy())

# Add custom scorer
class CustomScorer(ProviderScorer):
    def score_provider(self, ...):
        # Custom scoring logic
        pass

router.add_scorer(CustomScorer())
```

### 2. Unified Circuit Breaker Management

Circuit breakers are now centrally managed and integrated with both provider selection and execution:

```python
# Circuit breakers automatically protect providers
# No need for separate management in cascade router
```

### 3. Consistent Timeout Handling

Timeout configuration is unified across all execution strategies:

```python
timeout_config = TimeoutConfig(
    base_timeout_ms=10000,
    min_timeout_ms=3000,
    max_timeout_ms=30000,
    complexity_factor=0.5,
)
```

## Migration Steps

### 1. Update Imports

```python
# Old imports
from .query_routing.router import QueryRouter
from .query_routing.cascade_router import CascadeRouter

# New imports
from .query_routing.unified_router import UnifiedRouter
```

### 2. Update Server Initialization

Replace the old router initialization with the unified router:

```python
# In server.__init__
self.router = UnifiedRouter(
    providers=self.providers,
    timeout_config=TimeoutConfig(),
)
```

### 3. Update Search Logic

Replace the complex routing logic with the unified approach:

```python
# Old approach
if self._should_use_cascade(query, features, providers_to_use):
    # Cascade logic
else:
    # Parallel logic

# New approach
execution_results = await self.router.route_and_execute(
    query=query,
    features=features,
    budget=query.budget,
    strategy=strategy,  # Optional, auto-selected if None
)
```

### 4. Remove Redundant Code

- Remove `_should_use_cascade` method (logic now in UnifiedRouter)
- Remove separate parallel execution code
- Remove cascade router initialization

### 5. Update Configuration

If using advanced configuration, update to use the new unified approach:

```python
# Old
cascade_policy = CascadeExecutionPolicy(...)
cascade_router = CascadeRouter(..., execution_policy=cascade_policy)

# New
# Policy is part of the strategy
cascade_strategy = CascadeExecutionStrategy(policy=cascade_policy)
router.add_strategy("custom_cascade", cascade_strategy)
```

## Testing Considerations

### 1. Update Tests

- Replace tests for QueryRouter and CascadeRouter with UnifiedRouter tests
- Test custom strategy registration
- Test custom scorer registration
- Verify circuit breaker integration

### 2. Complete Migration

The legacy routers have been fully removed in favor of the unified router. The unified router maintains compatibility with existing provider interfaces and result formats. No changes are needed to:
- Provider implementations
- Result processing
- Cache management
- Metrics tracking

### 3. Performance Testing

Test the unified router performance under various scenarios:
- High-concurrency parallel execution
- Cascade execution with failures
- Dynamic timeout adjustments
- Circuit breaker behavior

## Advanced Features

### 1. Custom Execution Strategies

Create specialized execution strategies for specific use cases:

```python
class PriorityExecutionStrategy(ExecutionStrategy):
    """Execute providers based on priority with early termination."""
    
    async def execute(self, ...):
        # Custom priority-based execution
        pass

router.add_strategy("priority", PriorityExecutionStrategy())
```

### 2. Custom Scoring Systems

Implement domain-specific scoring logic:

```python
class DomainExpertScorer(ProviderScorer):
    """Score providers based on domain expertise."""
    
    def score_provider(self, ...):
        # Domain-specific scoring
        pass

router.add_scorer(DomainExpertScorer())
```

### 3. Dynamic Strategy Selection

Override automatic strategy selection for specific queries:

```python
# In SearchQuery advanced parameters
query = SearchQuery(
    query="test",
    advanced={
        "execution_strategy": "cascade",  # Force cascade execution
        "strategy_config": {...}  # Optional strategy configuration
    }
)
```

## Conclusion

The UnifiedRouter provides a more maintainable, extensible, and consistent approach to provider routing and execution. The migration simplifies the codebase while adding flexibility for future enhancements.