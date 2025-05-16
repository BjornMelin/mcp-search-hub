# MCP Search Hub TODO List

_Last updated: May 15, 2025 (all MCP server integrations and documentation complete)_

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

## Package and Version Updates (COMPLETED - May 15, 2025)

- [x] Update project dependencies to latest compatible versions

  - [x] Use uv to update fastmcp to latest version (2.3.4)
  - [x] Update httpx to latest version (0.28.1)
  - [x] Update pydantic to latest 2.x version (2.11.0)
  - [x] Update other dependencies as needed

- [x] Update pyproject.toml with specific version constraints
  - [x] Add dev dependencies section for testing tools
  - [x] Update Python version requirement to 3.11+
  - [x] Configure ruff settings for linting and formatting
  
**Notes**: All tests passing after update. Fixed several test issues due to dependency updates including merger logic, health metrics mocking, and FirecrawlProvider implementation.

## Provider Integration Improvements

### Strategy: Embed Official Provider MCP Servers Within MCP Search Hub

We've decided to embed official MCP servers for all providers within MCP Search Hub, creating a unified interface while leveraging provider-maintained functionality. This reduces maintenance burden and ensures we get the latest features directly from the providers.

#### Completed

- [x] Firecrawl: Successfully integrated official [firecrawl-mcp-server](https://github.com/mendableai/firecrawl-mcp-server) within MCP Search Hub
  - [x] Created MCP Python SDK wrapper for Firecrawl MCP server
  - [x] Exposed all Firecrawl tools through our unified server  
  - [x] Added tests for integrated functionality
  - [x] Dynamically register all available tools from the MCP server

- [x] Exa: Successfully integrated official [exa-mcp-server](https://github.com/exa-labs/exa-mcp-server) within MCP Search Hub
  - [x] Created MCP Python SDK wrapper following Firecrawl pattern
  - [x] Exposed all Exa tools (web_search_exa, research_paper_search, etc.)
  - [x] Implemented subprocess lifecycle management
  - [x] Added installation verification and auto-install
  - [x] Created comprehensive test suite with 15 test cases

#### Official MCP Servers Implementation Plan

- [x] Perplexity: Integrate [perplexity-mcp](https://github.com/ppl-ai/modelcontextprotocol) server
  - [x] Create MCP Python SDK wrapper similar to Firecrawl implementation
  - [x] Expose all Perplexity tools through unified server (ask, research, search)
  - [x] Add subprocess management for Node.js MCP server
  - [x] Implement automatic installation check
  - [x] Add comprehensive tests (23 tests passing)

- [x] Exa: Integrate [exa-mcp-server](https://github.com/exa-labs/exa-mcp-server)
  - [x] Create MCP Python SDK wrapper following Firecrawl pattern
  - [x] Expose all Exa tools (web_search_exa, research_paper_search, etc.)
  - [x] Implement subprocess lifecycle management
  - [x] Add installation verification and auto-install
  - [x] Create test suite for all exposed tools

- [x] Linkup: Integrate [python-mcp-server](https://github.com/LinkupPlatform/python-mcp-server)
  - [x] Create wrapper (Note: This is already a Python MCP server)
  - [x] Expose Linkup search functionality through unified interface
  - [x] Implement server lifecycle management
  - [x] Add comprehensive tests (22 tests passing)
  - [x] Handle Python-to-Python MCP communication

- [x] Tavily: Integrate [tavily-mcp](https://github.com/tavily-ai/tavily-mcp) server
  - [x] Create MCP Python SDK wrapper following established pattern
  - [x] Expose tavily-search and tavily-extract tools
  - [x] Implement Node.js subprocess management
  - [x] Add auto-installation capability
  - [x] Develop test coverage for all tools (23 tests passing)

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

- [x] Embed official [perplexity-mcp](https://github.com/ppl-ai/modelcontextprotocol) server
- [x] Create MCP wrapper following Firecrawl pattern
- [x] Expose perplexity_ask, perplexity_research, and search tools
- [x] Implement Node.js subprocess management
- [x] Add installation automation
- [x] Create comprehensive test suite (23 tests passing)

#### Exa Provider (Completed)

- [x] Embed official [exa-mcp-server](https://github.com/exa-labs/exa-mcp-server)
- [x] Create MCP wrapper with subprocess lifecycle management
- [x] Expose all Exa tools:
  - [x] web_search_exa
  - [x] research_paper_search
  - [x] company_research
  - [x] crawling
  - [x] competitor_finder
  - [x] linkedin_search
  - [x] wikipedia_search_exa
  - [x] github_search
- [x] Add auto-installation capability
- [x] Implement test coverage

#### Linkup Provider (Completed)

- [x] Embed official [python-mcp-server](https://github.com/LinkupPlatform/python-mcp-server)
- [x] Create wrapper (note: this is already a Python MCP server)
- [x] Handle Python-to-Python MCP communication
- [x] Expose search functionality through unified interface
- [x] Add configuration for premium content sources
- [x] Implement comprehensive tests (22 tests passing)

#### Tavily Provider (Completed)

- [x] Embed official [tavily-mcp](https://github.com/tavily-ai/tavily-mcp) server
- [x] Create MCP wrapper following established pattern
- [x] Expose tavily-search and tavily-extract tools
- [x] Implement Node.js subprocess management
- [x] Add automatic installation check
- [x] Develop test suite for all tools (23 tests passing)

## Query Routing Enhancements

- [x] Improve content type detection

  - [x] Add more sophisticated keyword detection
  - [x] Use regex patterns for better matching
  - [x] Add weighted scoring system for better accuracy
  - [x] Implement context-aware detection for ambiguous keywords
  - [x] Support detection of mixed/hybrid content types
  - [ ] Consider machine learning-based classification (future enhancement)

- [x] Enhance router scoring algorithm

  - [x] Update provider-specific scoring with more nuanced weights
  - [x] Add support for historical performance-based scoring
  - [x] Implement confidence scores for routing decisions

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

- [x] Implement exponential backoff retry logic for all API calls

  - [x] Add customizable retry configurations with environment variables
  - [x] Implement proper exception handling across providers
  - [x] Created retry.py module with configurable exponential backoff
  - [x] Added retry mixin for provider classes
  - [x] Updated all providers to use retry logic for HTTP requests
  - [x] Added comprehensive test suite for retry functionality
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

- [x] Create comprehensive unit tests

  - [x] Add provider-specific unit tests (Firecrawl, Exa)
  - [x] Implement query analyzer test suite
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

## Next Steps

Based on our Exa integration experience, here are the immediate next steps:

- [ ] Test the integrated providers with real API keys
  - [ ] Test Firecrawl MCP functionality end-to-end
  - [ ] Test Exa MCP functionality end-to-end
  - [ ] Document any issues or limitations found

- [ ] Continue MCP server integrations
  - [x] Perplexity MCP server integration (completed)
  - [x] Linkup Python MCP server integration (completed)
  - [x] Tavily MCP server integration (completed)

- [x] Update documentation
  - [x] Update CLAUDE.md with Exa, Linkup, and Tavily integration details
  - [x] Add configuration examples for each provider
  - [x] Document any special requirements and limitations
