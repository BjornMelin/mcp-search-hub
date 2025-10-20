# Changelog

All notable changes to this project will be documented in this file.

## [2025-05-16] - Routing System Simplification

## [2025-10-19] - FastMCP 2.12 Modernization

### Added
- **FastMCP-native server wiring**: Rebuilt `SearchServer` around `FastMCP` 2.12 with structured logging, retry, and sliding window rate limiting middleware.
- **Provider registry**: Introduced `mcp_search_hub.providers.registry.ProviderRegistry` and `MCPProviderSession` powered by `fastmcp.client.Client`.
- **Routing primitives**: Added `routing.classifier.QueryClassifier` and `routing.planner.RoutingPlanner` for tag-driven provider selection.
- **Caching & metrics**: Implemented `SearchCache` leveraging FastMCP storage utilities and a new `MetricsTracker` for observability.
- **Refreshed tests**: Added focused pytest suites covering cache behavior, routing, orchestrator caching, and server HTTP endpoints.

### Changed
- **Configuration**: Simplified settings to a single FastMCP-based provider pipeline with updated defaults and dependency hygiene.
- **Server entrypoints**: `main.py` now delegates to `SearchServer` for both HTTP and stdio transports with minimal CLI flags.
- **Dependency baseline**: Upgraded to `fastmcp>=2.12.5`, removed unused ML libraries, and aligned requirements/lockfiles.

### Removed
- **Legacy modules**: Deleted custom providers, middleware stack, routing shims, and result processing utilities replaced by library-native capabilities.
- **Back-compat toggles**: Removed legacy routing flags, cache fingerprint switches, and obsolete retry/budget code paths.

### Improved
- **Documentation**: Updated README to advertise the FastMCP 2.12 baseline and modern installation workflow.
- **Maintenance posture**: Flattened module structure and eliminated bespoke wrappers in favor of FastMCP primitives.

### Added
- **Unified Router**: Introduced `UnifiedRouter` class that consolidates `QueryRouter` and `CascadeRouter` functionality
- **Execution Strategies**: Created pluggable `ExecutionStrategy` pattern with:
  - `ParallelExecutionStrategy` for concurrent provider execution
  - `CascadeExecutionStrategy` for sequential failover execution
- **Pluggable Scoring**: Implemented `ProviderScorer` interface for customizable provider scoring
- **Circuit Breaker**: Added centralized circuit breaker pattern for all execution strategies
- **Dynamic Timeouts**: Centralized timeout management with dynamic adjustment based on query complexity
- **Migration Guide**: Created comprehensive migration documentation for transitioning to the unified system
- **Tests**: Added comprehensive test suite for the unified router system

### Changed
- **Server Implementation**: Updated `server.py` to use the new `UnifiedRouter`
- **Execution Flow**: Simplified routing and execution flow with unified `route_and_execute` method
- **Strategy Selection**: Automated strategy selection based on query characteristics

### Removed
- **Legacy Routers**: Fully removed `QueryRouter` and `CascadeRouter` implementations
- **Old Tests**: Removed redundant test files for legacy routers
- **Backward Compatibility**: Completely removed old router systems for simpler codebase

### Improved
- **Code Maintainability**: Eliminated code duplication between parallel and cascade routing
- **Extensibility**: Made the system more extensible with pluggable strategies and scorers
- **Error Handling**: Consistent error handling across all execution strategies

## [2025-05-16] - Provider Implementation Consolidation

### Added
- **Base MCP Provider**: Created unified `BaseMCPProvider` class to eliminate duplication in MCP server implementations
- **Unified Provider Management**: Standardized subprocess management, installation, and tool registration

### Changed
- **Provider Classes**: Refactored all provider classes to extend `BaseMCPProvider`
- **Import Structure**: Cleaned up imports by removing backward compatibility wrappers

### Removed
- **Backward Compatibility Wrappers**: Removed unnecessary wrapper classes for simpler code structure

### Improved
- **Code Maintainability**: Reduced code duplication across all provider implementations
- **Consistency**: Standardized behavior across Node.js and Python-based MCP servers