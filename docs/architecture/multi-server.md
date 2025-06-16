# Multi-Server MCP Architecture

## Overview

MCP Search Hub is designed to work seamlessly with official MCP servers from various providers. This approach offers several advantages:

1. **Reduced Maintenance**: We don't need to maintain complex provider-specific implementations
2. **Latest Features**: Official MCP servers are updated directly by providers
3. **Modular Architecture**: Each server can be updated or replaced independently
4. **Better Resource Management**: Separate processes for different providers

## Architecture Pattern

```plaintext
┌─────────────────┐
│  Claude Client  │
└─────────────────┘
         │
         ├──────────────────────────────────────┐
         │                                      │
┌────────▼────────┐                  ┌─────────▼─────────┐
│  MCP Search Hub │                  │ Official Provider │
│     Server      │                  │   MCP Servers     │
├─────────────────┤                  ├───────────────────┤
│ Multi-provider  │                  │ • Firecrawl MCP   │
│ search routing  │                  │ • Perplexity MCP  │
│ Result merging  │                  │ • Exa MCP         │
│ Cost optimize   │                  │ • Linkup MCP      │
└─────────────────┘                  └───────────────────┘
```

## Implementation Strategy

### 1. Core Search Hub Functionality

MCP Search Hub maintains its core value propositions:

- Intelligent query routing across multiple providers
- Result merging and ranking
- Cost optimization
- Unified search interface

### 2. Provider Integration

For each provider, we evaluate two options:

#### Option A: Use Official MCP Server (Preferred)

When a provider offers an official MCP server:

- Document how to install and configure it
- Provide example configurations
- Show how to use it alongside Search Hub

#### Option B: Basic Integration

When no official MCP server exists:

- Maintain minimal integration for search queries
- Focus on essential features only
- Monitor for official MCP server releases

## Current Provider Status

| Provider   | Official MCP Server | Status     | Notes                                                                          |
| ---------- | ------------------- | ---------- | ------------------------------------------------------------------------------ |
| Firecrawl  | ✅ Available        | Documented | Use [firecrawl-mcp-server](https://github.com/mendableai/firecrawl-mcp-server) |
| Perplexity | ❓ To be checked    | Pending    | Check official repos                                                           |
| Exa        | ❓ To be checked    | Pending    | Check official repos                                                           |
| Linkup     | ❓ To be checked    | Pending    | Check official repos                                                           |
| Tavily     | ❓ To be checked    | Pending    | Check official repos                                                           |

## Configuration Examples

### Single Server Configuration

For users who only need search aggregation:

```json
{
  "mcpServers": {
    "search": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Multi-Server Configuration

For users who want full capabilities:

```json
{
  "mcpServers": {
    "search-hub": {
      "url": "http://localhost:8000/mcp"
    },
    "firecrawl": {
      "command": ["npx", "firecrawl-mcp"],
      "env": {
        "FIRECRAWL_API_KEY": "your_api_key"
      }
    },
    "perplexity": {
      "command": ["npx", "perplexity-mcp"],
      "env": {
        "PERPLEXITY_API_KEY": "your_api_key"
      }
    }
  }
}
```

## Benefits of This Approach

1. **Separation of Concerns**: Each server handles its specialized domain
2. **Independent Updates**: Providers can update their servers without affecting Search Hub
3. **Reduced Complexity**: We focus on search aggregation, not provider implementation details
4. **Better Performance**: Parallel execution across multiple servers
5. **Flexibility**: Users can choose which servers to enable

## Migration Guide

For users currently using full Firecrawl integration through Search Hub:

1. Install the official Firecrawl MCP server:

   ```bash
   npm install -g firecrawl-mcp
   ```

2. Update your Claude configuration to include both servers

3. Use Search Hub for multi-provider search queries

4. Use Firecrawl MCP for advanced scraping features

## Future Considerations

As more providers release official MCP servers:

1. We'll update our documentation with integration guides
2. We may deprecate provider-specific code in favor of official servers
3. We'll focus more on the intelligent routing and aggregation layer
4. We'll explore ways to coordinate between multiple MCP servers

## Developer Guidelines

When adding new providers:

1. First check if an official MCP server exists
2. If yes, document how to use it with Search Hub
3. If no, implement minimal search integration only
4. Always prefer official servers over custom implementations

This approach ensures MCP Search Hub remains maintainable while providing users with the best possible experience through official, provider-maintained servers.
