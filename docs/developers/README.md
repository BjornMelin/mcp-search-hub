# Developer Documentation

Welcome to the MCP Search Hub developer documentation. This section is for developers who want to contribute to, extend, or integrate with MCP Search Hub.

## Quick Navigation

### Getting Started
- [Development Setup](development.md) - Set up your development environment
- [Contributing Guide](contributing.md) - How to contribute to the project
- [Architecture Overview](/docs/architecture/overview.md) - Understand the system design

### Core Concepts
- [MCP Protocol Integration](/docs/developers/mcp-protocol.md) - Understanding MCP server integration
- [Provider Architecture](/docs/developers/provider-architecture.md) - How providers work
- [Query Routing System](/docs/developers/routing-system.md) - Three-tier hybrid routing explained
- [Result Processing](/docs/developers/result-processing.md) - Merging and ranking algorithms

### API & Reference
- [API Reference](api-reference.md) - Complete tool documentation
- [Provider APIs](/docs/developers/provider-apis.md) - Provider-specific interfaces
- [Configuration API](/docs/developers/config-api.md) - Settings and configuration system
- [Python API Docs](/docs/reference/python-api.md) - Module and class documentation

### Extension & Integration
- [Adding New Providers](/docs/developers/new-provider-guide.md) - Step-by-step provider integration
- [Custom Routing Logic](/docs/developers/custom-routing.md) - Implementing custom routers
- [Plugin Development](/docs/developers/plugins.md) - Extending functionality
- [Integration Examples](/docs/developers/integration-examples.md) - Sample integrations

### Testing & Quality
- [Testing Strategy](/docs/developers/testing.md) - Test architecture and patterns
- [Performance Optimization](/docs/developers/performance.md) - Profiling and optimization
- [Code Standards](/docs/developers/code-standards.md) - Style guide and best practices
- [Debugging Guide](/docs/developers/debugging.md) - Troubleshooting development issues

### Architecture Decisions
- [ADR-001: Provider Integration](/docs/adrs/001-provider-integration-architecture.md)
- [ADR-002: Routing System](/docs/adrs/002-routing-system-design.md)
- [ADR-003: Caching Implementation](/docs/adrs/003-caching-implementation.md)
- [ADR-004: Middleware Architecture](/docs/adrs/004-middleware-architecture.md)
- [ADR-005: Provider Selection](/docs/adrs/005-provider-selection-strategy.md)

## Key Resources

### Design Documents
- [Consistent Service Interfaces](/docs/consistent-service-interfaces.md)
- [Architectural Patterns](/docs/consistent-architectural-patterns.md)
- [Middleware Design](/docs/architecture/middleware.md)
- [Caching Strategy](/docs/architecture/caching.md)

### Implementation Guides
- [Provider Management](/docs/provider-management.md)
- [Error Handling](/docs/unified-error-handling.md)
- [Retry Mechanisms](/docs/retry.md)
- [Configuration System](/docs/standardized-configuration.md)

## Development Workflow

1. **Setup**: Clone repo → Install dependencies → Configure environment
2. **Develop**: Create feature branch → Write tests → Implement feature
3. **Test**: Run tests → Check coverage → Lint code
4. **Submit**: Create PR → Pass CI → Get review → Merge

## Getting Help

- Review existing [issues](https://github.com/yourusername/mcp-search-hub/issues)
- Join our [developer discussions](https://github.com/yourusername/mcp-search-hub/discussions)
- Check the [troubleshooting guide](/docs/developers/troubleshooting.md)