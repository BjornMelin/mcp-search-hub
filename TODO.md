# MCP Search Hub TODO List

_Last updated: May 15, 2025_

## Core Functionality

- [x] Implement stdin/stdout transport option for command-line usage

  - [x] Add transport parameter to main.py with choice between "streamable-http" and "stdio"
  - [x] Implement stdio transport handling in FastMCP server initialization
  - [x] Update shutdown handler for stdio transport
  - [x] Add CLI argument parser to support transport options and API keys

- [x] Add support for returning raw content from providers when requested

  - [x] Update SearchQuery model to add raw_content: bool parameter
  - [x] Modify provider implementations to include full content when raw_content=True
  - [x] Update result processing to handle raw content appropriately

- [x] Add health check and metrics endpoints
  - [x] Implement health check route using @mcp.custom_route("/health")
  - [x] Create metrics endpoint for tracking usage statistics
  - [x] Add provider status checks to health endpoint

## Package and Version Updates

- [ ] Update project dependencies to latest compatible versions

  - [ ] Use uv to update fastmcp to latest version (2.3+)
  - [ ] Update httpx to latest version (0.27+)
  - [ ] Update pydantic to latest 2.x version
  - [ ] Update other dependencies as needed

- [ ] Update pyproject.toml with specific version constraints
  - [ ] Add dev dependencies section for testing tools
  - [ ] Update Python version requirement to 3.10+ or 3.11+
  - [ ] Configure ruff settings for linting and formatting

## Provider Integration Improvements

### Strategy: Embed Official Provider MCP Servers Within MCP Search Hub

We've decided to embed official MCP servers for all providers within MCP Search Hub, creating a unified interface while leveraging provider-maintained functionality. This reduces maintenance burden and ensures we get the latest features directly from the providers.

#### Completed

- [x] Firecrawl: Successfully integrated official [firecrawl-mcp-server](https://github.com/mendableai/firecrawl-mcp-server) within MCP Search Hub
  - [x] Created MCP Python SDK wrapper for Firecrawl MCP server
  - [x] Exposed all Firecrawl tools through our unified server  
  - [x] Added tests for integrated functionality
  - [x] Dynamically register all available tools from the MCP server

#### Official MCP Servers Implementation Plan

- [ ] Perplexity: Integrate [perplexity-mcp](https://github.com/ppl-ai/modelcontextprotocol) server
  - [ ] Create MCP Python SDK wrapper similar to Firecrawl implementation
  - [ ] Expose all Perplexity tools through unified server (ask, research, search)
  - [ ] Add subprocess management for Node.js MCP server
  - [ ] Implement automatic installation check
  - [ ] Add comprehensive tests

- [ ] Exa: Integrate [exa-mcp-server](https://github.com/exa-labs/exa-mcp-server)
  - [ ] Create MCP Python SDK wrapper following Firecrawl pattern
  - [ ] Expose all Exa tools (web_search_exa, research_paper_search, etc.)
  - [ ] Implement subprocess lifecycle management
  - [ ] Add installation verification and auto-install
  - [ ] Create test suite for all exposed tools

- [ ] Linkup: Integrate [python-mcp-server](https://github.com/LinkupPlatform/python-mcp-server)
  - [ ] Create wrapper (Note: This is already a Python MCP server)
  - [ ] Expose Linkup search functionality through unified interface
  - [ ] Implement server lifecycle management
  - [ ] Add comprehensive tests
  - [ ] Handle Python-to-Python MCP communication

- [ ] Tavily: Integrate [tavily-mcp](https://github.com/tavily-ai/tavily-mcp) server
  - [ ] Create MCP Python SDK wrapper following established pattern
  - [ ] Expose tavily-search and tavily-extract tools
  - [ ] Implement Node.js subprocess management
  - [ ] Add auto-installation capability
  - [ ] Develop test coverage for all tools

#### Implementation Steps for Each Provider

For each provider integration, follow these steps:

1. Create a new provider module (e.g., `providers/perplexity_mcp.py`)
2. Implement MCP wrapper class with:
   - Installation check (`_check_installation`)
   - Installation method (`_install_server`)
   - Server connection (`initialize`)
   - Tool invocation proxy (`invoke_tool`)
   - Cleanup handling
3. Update `server.py` to dynamically register provider tools
4. Add comprehensive tests
5. Update documentation with configuration instructions

### Provider-Specific Updates

#### Firecrawl Provider (Completed)

- [x] Successfully embedded official [firecrawl-mcp-server](https://github.com/mendableai/firecrawl-mcp-server)
- [x] Created MCP Python SDK wrapper for subprocess management
- [x] Exposed all Firecrawl tools through unified interface
- [x] Added comprehensive tests for all functionality

#### Perplexity Provider

- [ ] Embed official [perplexity-mcp](https://github.com/ppl-ai/modelcontextprotocol) server
- [ ] Create MCP wrapper following Firecrawl pattern
- [ ] Expose perplexity_ask, perplexity_research, and search tools
- [ ] Implement Node.js subprocess management
- [ ] Add installation automation
- [ ] Create comprehensive test suite

#### Exa Provider

- [ ] Embed official [exa-mcp-server](https://github.com/exa-labs/exa-mcp-server)
- [ ] Create MCP wrapper with subprocess lifecycle management
- [ ] Expose all Exa tools:
  - [ ] web_search_exa
  - [ ] research_paper_search
  - [ ] company_research
  - [ ] crawling
  - [ ] competitor_finder
  - [ ] linkedin_search
  - [ ] wikipedia_search_exa
  - [ ] github_search
- [ ] Add auto-installation capability
- [ ] Implement test coverage

#### Linkup Provider

- [ ] Embed official [python-mcp-server](https://github.com/LinkupPlatform/python-mcp-server)
- [ ] Create wrapper (note: this is already a Python MCP server)
- [ ] Handle Python-to-Python MCP communication
- [ ] Expose search functionality through unified interface
- [ ] Add configuration for premium content sources
- [ ] Implement comprehensive tests

#### Tavily Provider

- [ ] Embed official [tavily-mcp](https://github.com/tavily-ai/tavily-mcp) server
- [ ] Create MCP wrapper following established pattern
- [ ] Expose tavily-search and tavily-extract tools
- [ ] Implement Node.js subprocess management
- [ ] Add automatic installation check
- [ ] Develop test suite for all tools

## Query Routing Enhancements

- [ ] Improve content type detection

  - [ ] Add more sophisticated keyword detection
  - [ ] Use regex patterns for better matching
  - [ ] Consider machine learning-based classification

- [ ] Enhance router scoring algorithm

  - [ ] Update provider-specific scoring with more nuanced weights
  - [ ] Add support for historical performance-based scoring
  - [ ] Implement confidence scores for routing decisions

- [ ] Implement advanced routing patterns
  - [ ] Add multi-provider cascade routing (try secondary if primary fails)
  - [ ] Implement specialized routing for hybrid queries
  - [ ] Add dynamic provider timeouts based on query complexity

## Result Processing Improvements

- [ ] Enhance deduplication with URL normalization

  - [ ] Add smart URL normalization for better deduplication
  - [ ] Implement fuzzy matching for near-duplicate detection
  - [ ] Add content-based similarity detection

- [ ] Improve result ranking

  - [ ] Update provider quality weights based on performance data
  - [ ] Add recency factoring for time-sensitive queries
  - [ ] Implement source credibility scoring

- [ ] Add metadata enrichment
  - [ ] Implement consistent metadata schema across providers
  - [ ] Add source attribution and citation formatting
  - [ ] Extract and normalize dates from varied formats

## Performance & Reliability

- [ ] Implement exponential backoff retry logic for all API calls

  - [ ] Add customizable retry configurations
  - [ ] Implement proper exception handling across providers
  - [ ] Add circuit breaker pattern for failing providers

- [ ] Enhance caching system

  - [ ] Implement tiered caching strategy with different TTLs
  - [ ] Add cache invalidation hooks
  - [ ] Support partial cache updates

- [ ] Add rate limiting and quota management
  - [ ] Implement provider-specific rate limiters
  - [ ] Add budget-tracking for API usage costs
  - [ ] Create usage reporting for quota management

## Testing & Documentation

- [ ] Create comprehensive unit tests

  - [ ] Add provider-specific unit tests
  - [ ] Implement query analyzer test suite
  - [ ] Create router test scenarios

- [ ] Add integration tests

  - [ ] Create end-to-end test suite with mocked responses
  - [ ] Add performance benchmark tests
  - [ ] Implement CI pipeline for automated testing

- [x] Improve documentation
  - [x] Create README.md with installation and usage instructions
  - [x] Add configuration guide for different environments
  - [x] Create example configurations for MCP clients
  - [x] Document provider-specific features and limitations
  - [x] Create REFERENCES.md with comprehensive documentation links for all providers and technologies

## MCP Client Integration

- [x] Create client setup instructions for various MCP clients

  - [x] Add Claude Desktop configuration guide
  - [x] Create Claude Code integration instructions
  - [x] Add VS Code client configuration
  - [x] Document Cursor and Windsurf integration

- [x] Add platform-specific installation instructions
  - [x] Create Windows installation guide
  - [x] Add WSL on Windows setup instructions
  - [x] Document macOS installation process
  - [x] Add Docker deployment guide

## Deployment & Operations

- [ ] Update Docker configuration

  - [ ] Use multi-stage build for smaller images
  - [ ] Add proper health checks to Docker configuration
  - [ ] Create Docker Compose development and production setups
  - [ ] Configure proper environment variable handling

- [ ] Add logging and observability

  - [ ] Implement structured logging
  - [ ] Add request tracing with correlation IDs
  - [ ] Create error reporting system
  - [ ] Set up monitoring hooks

- [ ] Support additional deployment options
  - [ ] Create Kubernetes configuration
  - [ ] Add serverless deployment support
  - [ ] Document hosting provider options
