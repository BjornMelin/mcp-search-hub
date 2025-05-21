# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP Search Hub is an intelligent multi-provider search aggregation server built on FastMCP 2.0. It embeds official MCP servers from five search providers (Linkup, Exa, Perplexity, Tavily, and Firecrawl) within a unified interface, intelligently routes queries to the most appropriate provider(s), and combines/ranks results for optimal relevance.

### Architectural Approach: Embedded MCP Servers with Generic Implementation

We embed official provider MCP servers within MCP Search Hub and use a generic implementation pattern to eliminate code duplication. All providers are now successfully integrated:

- **Firecrawl**: Embedded [firecrawl-mcp-server](https://github.com/mendableai/firecrawl-mcp-server)
- **Perplexity**: Embedded [perplexity-mcp](https://github.com/ppl-ai/modelcontextprotocol)
- **Exa**: Embedded [exa-mcp-server](https://github.com/exa-labs/exa-mcp-server)
- **Linkup**: Embedded [python-mcp-server](https://github.com/LinkupPlatform/python-mcp-server)
- **Tavily**: Embedded [tavily-mcp](https://github.com/tavily-ai/tavily-mcp)

All providers now use `GenericMCPProvider` base class which:
- Handles installation, initialization, and cleanup uniformly
- Uses configuration-driven provider settings from `provider_config.py`
- Provides common parameter preparation and result processing
- Eliminates hundreds of lines of duplicated code

This approach ensures we get the latest features directly from the providers while maintaining a unified interface and maximally simplified codebase.

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
     - `FirecrawlMCPProvider`: Embeds firecrawl-mcp-server (Node.js)
     - `PerplexityMCPProvider`: Embeds perplexity-mcp (Node.js)
     - `ExaMCPProvider`: Embeds exa-mcp-server (Node.js)
     - `LinkupMCPProvider`: Embeds python-mcp-server (Python)
     - `TavilyMCPProvider`: Embeds tavily-mcp (Node.js)

3. **Query Routing**

   - `QueryAnalyzer`: Extracts features from queries to determine content type and complexity
   - `UnifiedRouter`: Unified routing system that replaces the legacy QueryRouter and CascadeRouter
     - Supports pluggable execution strategies (parallel, cascade)
     - Integrates circuit breaker pattern for provider protection
     - Dynamic timeout management based on query complexity
   - `CostOptimizer`: Optimizes provider selection for cost efficiency

4. **Result Processing**

   - `ResultMerger`: Combines, deduplicates, and ranks results from multiple providers
     - Multi-factor ranking algorithm (provider quality, result score, consensus boost)
     - Raw content merging that preserves metadata
     - Configurable provider weights
   - `Deduplication`: Removes duplicate results based on normalized URLs

5. **Utilities**
   - `QueryCache`: Caches search results for improved performance
   - Config management with environment variables

### Data Flow

1. Client sends search query to the FastMCP server
2. QueryAnalyzer extracts features from the query
3. UnifiedRouter selects providers and execution strategy based on query characteristics
4. Selected providers execute search via their embedded MCP servers using the chosen strategy
5. MCP wrappers handle communication with provider MCP servers
6. Results are combined, ranked, and deduplicated
7. Final combined results are returned to the client

### MCP Server Integration Pattern

When adding a new provider with MCP server:

1. Add provider configuration to `providers/provider_config.py`
2. Create a minimal wrapper in `providers/<provider>_mcp.py` that inherits from `GenericMCPProvider`
3. The generic base handles all standard functionality:
   - Installation check and execution
   - Server connection and initialization
   - Parameter preparation and result processing
   - Tool invocation and cleanup
4. Only override methods if the provider requires special handling
5. Update `server.py` to register the new provider (tools are registered dynamically)
6. Add comprehensive tests
7. Update documentation

## Configuration

The application uses environment variables for configuration:

- Provider API keys: `LINKUP_API_KEY`, `EXA_API_KEY`, etc.
- Provider enablement: `LINKUP_ENABLED`, `EXA_ENABLED`, etc.
- Timeouts: `LINKUP_TIMEOUT`, `EXA_TIMEOUT`, etc.
- Server: `HOST`, `PORT`
- Misc: `LOG_LEVEL`, `CACHE_TTL`, `DEFAULT_BUDGET`

### Rate Limiting and Budget Configuration

Provider rate limiting and budget settings are configured in `provider_config.py`:

```python
"provider_name": {
    # Rate limits
    "rate_limits": RateLimitConfig(
        requests_per_minute=60,   # Maximum requests per minute
        requests_per_hour=500,    # Maximum requests per hour
        requests_per_day=5000,    # Maximum requests per day
        concurrent_requests=10,   # Maximum concurrent requests
        cooldown_period=5,        # Seconds to wait when rate limited
    ),
    # Budget config
    "budget": BudgetConfig(
        default_query_budget=Decimal("0.02"),  # Max cost per query
        daily_budget=Decimal("10.00"),         # Max daily cost
        monthly_budget=Decimal("150.00"),      # Max monthly cost
        enforce_budget=True,                   # Whether to enforce budgets
    ),
    # Base cost in USD per query
    "base_cost": Decimal("0.01"),  # Base cost for pricing calculations
}
```

The following environment variables can be used to customize rate limiting and budget tracking:

```bash
# Provider Rate Limits (example for EXA)
EXA_REQUESTS_PER_MINUTE=60
EXA_REQUESTS_PER_HOUR=500
EXA_REQUESTS_PER_DAY=5000
EXA_CONCURRENT_REQUESTS=10
EXA_COOLDOWN_PERIOD=5

# Provider Budgets (example for EXA)
EXA_DEFAULT_QUERY_BUDGET=0.02
EXA_DAILY_BUDGET=10.00
EXA_MONTHLY_BUDGET=150.00
EXA_ENFORCE_BUDGET=true
EXA_BASE_COST=0.01
```

### Provider-Specific Configuration

Each provider requires specific environment variables and may have unique configuration options.

#### Firecrawl Configuration

```bash
# Required
FIRECRAWL_API_KEY=fc_api_key_xxxxx

# Optional
FIRECRAWL_ENABLED=true      # Default: true
FIRECRAWL_TIMEOUT=30000     # Default: 30000 (ms)
```

Available tools:
- `firecrawl_scrape`: Scrape content from a URL
- `firecrawl_map`: Discover URLs from a starting point
- `firecrawl_crawl`: Start an asynchronous crawl
- `firecrawl_check_crawl_status`: Check crawl status
- `firecrawl_search`: Search the web
- `firecrawl_extract`: Extract structured information
- `firecrawl_deep_research`: Conduct deep research
- `firecrawl_generate_llmstxt`: Generate LLMs.txt file

#### Exa Configuration

```bash
# Required
EXA_API_KEY=exa_api_key_xxxxx

# Optional
EXA_ENABLED=true      # Default: true
EXA_TIMEOUT=15000     # Default: 15000 (ms)
```

Available tools:
- `exa_search`: Search the web
- `exa_research_papers`: Search for research papers
- `exa_company_research`: Research companies
- `exa_competitor_finder`: Find competitors for a company
- `exa_linkedin_search`: Search LinkedIn
- `exa_wikipedia_search`: Search Wikipedia
- `exa_github_search`: Search GitHub
- `exa_crawl`: Crawl a URL

#### Perplexity Configuration

```bash
# Required
PERPLEXITY_API_KEY=pplx-xxxxxx

# Optional
PERPLEXITY_ENABLED=true      # Default: true
PERPLEXITY_TIMEOUT=20000     # Default: 20000 (ms)
```

Available tools:
- `perplexity_ask`: Ask a question with web search
- `perplexity_research`: Research a topic in depth
- `perplexity_reason`: Perform reasoning tasks

#### Linkup Configuration

```bash
# Required
LINKUP_API_KEY=lp_xxxxxxxx

# Optional
LINKUP_ENABLED=true      # Default: true
LINKUP_TIMEOUT=10000     # Default: 10000 (ms)
```

Available tools:
- `linkup_search_web`: Search the web with depth options

#### Tavily Configuration

```bash
# Required
TAVILY_API_KEY=tvly-xxxxxxxx

# Optional
TAVILY_ENABLED=true      # Default: true
TAVILY_TIMEOUT=10000     # Default: 10000 (ms)
```

Available tools:
- `tavily_search`: Search the web with basic/advanced options
- `tavily_extract`: Extract content from URLs

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

## Provider MCP Server Details

### Installation and Dependencies

MCP Search Hub automatically handles the installation of each provider's MCP server. You don't need to install them manually, but here are the details for reference:

#### Node.js MCP Servers (Firecrawl, Exa, Perplexity, Tavily)

These providers use Node.js MCP servers that are installed automatically via npm/npx:

```bash
# Firecrawl
npm install -g firecrawl-mcp-server

# Exa
npm install -g @modelcontextprotocol/server-exa

# Perplexity
npm install -g @ppl-ai/perplexity-mcp

# Tavily
npm install -g tavily-mcp@0.2.0
```

#### Python MCP Server (Linkup)

Linkup uses a Python MCP server that is installed automatically via pip:

```bash
pip install mcp-search-linkup
```

### Example .env File

Create a `.env` file in the project root with your API keys:

```bash
# Server configuration
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
# Caching configuration
CACHE_TTL=300                    # Legacy memory cache TTL in seconds
CACHE_MEMORY_TTL=300             # Memory cache TTL for tiered cache (5 minutes)
CACHE_REDIS_TTL=3600             # Redis cache TTL for tiered cache (1 hour)
REDIS_URL=redis://localhost:6379  # Redis connection URL
REDIS_CACHE_ENABLED=false         # Set to 'true' to enable Redis caching
CACHE_PREFIX=search:              # Prefix for Redis cache keys
CACHE_FINGERPRINT_ENABLED=true    # Enable semantic fingerprinting for queries
CACHE_CLEAN_INTERVAL=600          # Cache cleanup interval (10 minutes)
# Budget
DEFAULT_BUDGET=0.1

# Firecrawl
FIRECRAWL_API_KEY=fc_api_key_xxxxx
FIRECRAWL_ENABLED=true
FIRECRAWL_TIMEOUT=30000

# Exa
EXA_API_KEY=exa_api_key_xxxxx
EXA_ENABLED=true
EXA_TIMEOUT=15000

# Perplexity
PERPLEXITY_API_KEY=pplx-xxxxxx
PERPLEXITY_ENABLED=true
PERPLEXITY_TIMEOUT=20000

# Linkup
LINKUP_API_KEY=lp_xxxxxxxx
LINKUP_ENABLED=true
LINKUP_TIMEOUT=10000

# Tavily
TAVILY_API_KEY=tvly-xxxxxxxx
TAVILY_ENABLED=true
TAVILY_TIMEOUT=10000
```

### Special Requirements and Limitations

- **Node.js**: Required for Firecrawl, Exa, Perplexity, and Tavily integrations (v16+ recommended)
- **Disk Space**: Each provider's MCP server installation requires additional disk space
- **Memory**: Running all providers simultaneously may require 1GB+ of memory
- **API Limits**: Be aware of each provider's rate limits and pricing structure
- **Initialization Time**: First request to each provider may take longer as the MCP server is initialized

## Client Integration Examples

### Claude Desktop Configuration

To use MCP Search Hub with Claude Desktop, add the following configuration to your Claude Desktop configuration file:

```json
{
  "mcpServers": {
    "mcp-search-hub": {
      "command": "python",
      "args": ["-m", "mcp_search_hub.main", "--transport", "stdio"],
      "env": {
        "FIRECRAWL_API_KEY": "fc_api_key_xxxxx",
        "EXA_API_KEY": "exa_api_key_xxxxx",
        "PERPLEXITY_API_KEY": "pplx-xxxxxx",
        "LINKUP_API_KEY": "lp_xxxxxxxx",
        "TAVILY_API_KEY": "tvly-xxxxxxxx"
      }
    }
  }
}
```

### Claude Code Configuration

To use MCP Search Hub with Claude Code CLI, add the following to your Claude Code configuration:

```json
{
  "mcpServers": {
    "mcp-search-hub": {
      "command": "python",
      "args": ["-m", "mcp_search_hub.main", "--transport", "stdio"],
      "env": {
        "FIRECRAWL_API_KEY": "fc_api_key_xxxxx",
        "EXA_API_KEY": "exa_api_key_xxxxx",
        "PERPLEXITY_API_KEY": "pplx-xxxxxx",
        "LINKUP_API_KEY": "lp_xxxxxxxx",
        "TAVILY_API_KEY": "tvly-xxxxxxxx"
      }
    }
  }
}
```

With this configuration, Claude will have access to all search providers through a unified interface.
