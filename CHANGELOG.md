# Changelog

All notable changes to this project will be documented in this file.

## [2025-05-16] - Routing System Simplification

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