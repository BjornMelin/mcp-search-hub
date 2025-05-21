# ADR-001: Provider Integration Architecture

## Status

Accepted

## Context

MCP Search Hub needed to integrate multiple search providers (Exa, Tavily, Linkup, Perplexity, Firecrawl) into a unified interface. The challenge was to support both Python and Node.js MCP servers while maintaining clean abstractions and minimizing code duplication.

Key requirements:
- Support for both Python and Node.js MCP server implementations
- Unified interface for all providers regardless of underlying technology
- Minimal code duplication across provider implementations
- Easy addition of new providers
- Proper resource management and cleanup
- Configuration-driven provider management

## Decision

We decided to implement an **Embedded MCP Server Architecture** with a **Generic Provider Pattern**:

1. **Embed Official MCP Servers**: Use the official MCP servers from each provider as subprocess implementations
2. **Generic Base Class**: Create `GenericMCPProvider` base class to eliminate code duplication
3. **Configuration-Driven**: Use `provider_config.py` for centralized provider configuration
4. **Minimal Provider Classes**: Reduce provider implementations to 4-line classes that inherit from the generic base

### Architecture Components

- `GenericMCPProvider`: Base class handling subprocess management, installation, tool registration
- `provider_config.py`: Centralized configuration for all provider settings
- Provider-specific classes: Minimal implementations that only specify configuration
- Dynamic tool registration: Automatic discovery and registration of provider tools

## Consequences

### Positive

- **Eliminated 750+ lines** of redundant code across provider implementations
- **Simplified maintenance**: Provider-specific code reduced to essential configuration
- **Consistent behavior**: All providers use identical initialization and cleanup patterns
- **Easy extension**: Adding new providers requires minimal code
- **Official compatibility**: Using official MCP servers ensures latest features and compatibility
- **Resource management**: Unified subprocess lifecycle management

### Negative

- **Additional dependencies**: Requires Node.js for most providers
- **Initialization complexity**: More complex startup sequence with subprocess management
- **Debugging overhead**: Errors may occur in subprocess communication layer

### Trade-offs

- **Simplicity vs. Control**: Traded direct API control for code simplicity and maintainability
- **Performance vs. Maintainability**: Subprocess overhead acceptable for significant maintenance benefits
- **Flexibility vs. Consistency**: Standardized approach may limit provider-specific optimizations

## Implementation Details

```python
# Before: Provider-specific implementations with hundreds of lines each
class ExaProvider(SearchProvider):
    # 200+ lines of implementation details...

# After: Minimal configuration-driven implementation
class ExaMCPProvider(GenericMCPProvider):
    def __init__(self):
        super().__init__("exa")
```

The generic base class handles:
- Installation verification and execution
- Subprocess management (Node.js/Python)
- Tool discovery and registration
- Parameter preparation and validation
- Result processing and error handling
- Resource cleanup

## Alternatives Considered

1. **Direct API Integration**: Implementing each provider's REST API directly
   - Rejected: High maintenance overhead, frequent API changes
   
2. **Plugin Architecture**: Dynamic loading of provider plugins
   - Rejected: Increased complexity without significant benefits
   
3. **Microservices**: Separate service for each provider
   - Rejected: Operational complexity for minimal deployment scenarios

## Related Decisions

- [ADR-002: Routing System Design](./002-routing-system-design.md)
- [ADR-004: Middleware Architecture](./004-middleware-architecture.md)