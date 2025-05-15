# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP Search Hub is an intelligent multi-provider search aggregation server built on FastMCP 2.0. It integrates five search providers (Linkup, Exa, Perplexity, Tavily, and Firecrawl) under a unified API, intelligently routes queries to the most appropriate provider(s), and combines/ranks results for optimal relevance.

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

   - `SearchServer` (server.py): FastMCP server implementation that registers tools and orchestrates the search process

2. **Provider Layer**

   - Base `SearchProvider` interface with implementations for each service:
     - `LinkupProvider`: Factual information (91.0% SimpleQA accuracy)
     - `ExaProvider`: Academic content and semantic search (90.04% SimpleQA accuracy)
     - `PerplexityProvider`: Current events and LLM processing (86% accuracy)
     - `TavilyProvider`: RAG-optimized results (73% SimpleQA accuracy)
     - `FirecrawlProvider`: Deep content extraction and scraping

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
4. Selected providers execute the search in parallel
5. Results are combined, ranked, and deduplicated
6. Final combined results are returned to the client

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
