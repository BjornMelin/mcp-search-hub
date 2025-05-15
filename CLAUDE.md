# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP Search Hub is an intelligent multi-provider search aggregation server built on FastMCP 2.0. It embeds official MCP servers from five search providers (Linkup, Exa, Perplexity, Tavily, and Firecrawl) within a unified interface, intelligently routes queries to the most appropriate provider(s), and combines/ranks results for optimal relevance.

### Architectural Approach: Embedded MCP Servers

We embed official provider MCP servers within MCP Search Hub rather than implementing features ourselves:
- **Firecrawl**: Successfully embedded [firecrawl-mcp-server](https://github.com/mendableai/firecrawl-mcp-server)
- **Perplexity**: In progress - [perplexity-mcp](https://github.com/ppl-ai/modelcontextprotocol)
- **Exa**: In progress - [exa-mcp-server](https://github.com/exa-labs/exa-mcp-server)
- **Linkup**: In progress - [python-mcp-server](https://github.com/LinkupPlatform/python-mcp-server)
- **Tavily**: In progress - [tavily-mcp](https://github.com/tavily-ai/tavily-mcp)

## Development Commands

### Environment Setup

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies using uv (preferred)
uv pip install -r requirements.txt

# Alternative: pip install
pip install -r requirements.txt
```

### Running the Server

```bash
# Run the server directly
python -m mcp_search_hub.main

# Run with Docker Compose
docker-compose up -d
```

### Testing

```bash
# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=mcp_search_hub

# Run a specific test
uv run pytest tests/test_analyzer.py

# Run a specific test function
uv run pytest tests/test_analyzer.py::test_query_analyzer
```

### Code Quality

```bash
# Run ruff linter
ruff check .

# Run ruff with auto-fixes
ruff check --fix .

# Run ruff formatter
ruff format .

# Sort imports
ruff check --select I --fix .
```

## Architecture

### Core Components

1. **Server Layer**

   - `SearchServer` (server.py): FastMCP server implementation that registers tools and orchestrates the search process, including dynamic registration of embedded MCP server tools

2. **Provider Layer**

   - Base `SearchProvider` interface with implementations for each service
   - MCP Wrappers for embedded servers:
     - `FirecrawlMCPProvider`: Embeds firecrawl-mcp-server (completed)
     - `PerplexityMCPProvider`: Embeds perplexity-mcp (in progress)
     - `ExaMCPProvider`: Embeds exa-mcp-server (in progress)
     - `LinkupMCPProvider`: Embeds python-mcp-server (in progress)
     - `TavilyMCPProvider`: Embeds tavily-mcp (in progress)

3. **Query Routing**

   - `QueryAnalyzer`: Extracts features from queries to determine content type and complexity
   - `QueryRouter`: Selects providers based on query features and budget constraints
   - `CostOptimizer`: Optimizes provider selection for cost efficiency

4. **Result Processing**

   - `ResultMerger`: Combines results from multiple providers
   - `Ranker`: Ranks and sorts results for relevance
   - `Deduplication`: Removes duplicate results

5. **Utilities**
   - `QueryCache`: Caches search results for improved performance
   - Config management with environment variables

### Data Flow

1. Client sends search query to the FastMCP server
2. QueryAnalyzer extracts features from the query
3. QueryRouter selects appropriate providers
4. Selected providers execute search via their embedded MCP servers
5. MCP wrappers handle communication with provider MCP servers
6. Results are combined, ranked, and deduplicated
7. Final combined results are returned to the client

### MCP Server Integration Pattern

When implementing MCP server wrappers:

1. Create a new wrapper module (e.g., `providers/perplexity_mcp.py`)
2. Implement the MCP wrapper class with:
   - Installation check (`_check_installation`)
   - Installation method (`_install_server`)
   - Server connection (`initialize`)
   - Tool invocation proxy (`invoke_tool`)
   - Cleanup handling
3. Update `server.py` to dynamically register provider tools
4. Add comprehensive tests
5. Update documentation

## Configuration

The application uses environment variables for configuration:

- Provider API keys: `LINKUP_API_KEY`, `EXA_API_KEY`, etc.
- Provider enablement: `LINKUP_ENABLED`, `EXA_ENABLED`, etc.
- Timeouts: `LINKUP_TIMEOUT`, `EXA_TIMEOUT`, etc.
- Server: `HOST`, `PORT`
- Misc: `LOG_LEVEL`, `CACHE_TTL`, `DEFAULT_BUDGET`

## Best Practices

- Always follow type hints (the project uses Python type annotations throughout)
- Maintain async/await patterns consistently
- Handle errors and timeouts appropriately
- Write tests for new components, aiming for >90% coverage
- Keep provider implementations consistent with the base class interface
- Use Pydantic for data validation and serialization
- Follow the established MCP server integration pattern for new providers
- Ensure proper cleanup of subprocess resources
- Handle both Node.js and Python MCP servers appropriately
- Dynamically register all provider tools with consistent naming
