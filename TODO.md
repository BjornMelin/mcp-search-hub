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

### Strategy: Use Official Provider MCP Servers When Available

We've decided to use official MCP servers for providers that offer them, while maintaining basic integration for search functionality. This reduces maintenance burden and ensures we get the latest features directly from the providers.

#### Completed

- [x] Document Firecrawl MCP server integration alongside Search Hub
- [x] Create multi-server configuration examples for Claude clients
- [x] Update README with instructions for using multiple MCP servers

#### Official MCP Servers Available

- [x] Firecrawl: Successfully integrated official [firecrawl-mcp-server](https://github.com/mendableai/firecrawl-mcp-server) within MCP Search Hub
  - [x] Created MCP Python SDK wrapper for Firecrawl MCP server
  - [x] Exposed all Firecrawl tools through our unified server
  - [x] Added tests for integrated functionality
- [ ] Check if Perplexity has an official MCP server
- [ ] Check if Exa has an official MCP server  
- [ ] Check if Linkup has an official MCP server
- [ ] Check if Tavily has an official MCP server

#### Provider Updates (for basic search integration)

- [ ] Update all providers with latest API interfaces
- [ ] Enhance error handling and retry logic
- [ ] Ensure compatibility with official MCP servers

### Provider-Specific Updates

#### Firecrawl Provider

- [x] ~~Implement full tool suite~~ (Using official MCP server instead)
- [x] Document integration with official firecrawl-mcp-server
- [x] Successfully embed Firecrawl MCP server within MCP Search Hub
- [x] Maintain basic search integration for unified search interface

#### Exa Provider

- [ ] Check for official MCP server availability
- [ ] Update to Exa API v2 for basic search
  - [ ] Add support for time range filtering
  - [ ] Implement highlight extraction
  - [ ] Update response parsing to support new result fields

#### Linkup Provider

- [ ] Check for official MCP server availability
- [ ] Update to handle advanced output formats (aggregated, curated)
- [ ] Add support for domain filtering (allowed/blocked domains)
- [ ] Implement request chunking for deep searches

#### Perplexity Provider

- [ ] Check for official MCP server availability
- [ ] Update with latest API model options (including "sonar-pro" model)
- [ ] Maintain basic search integration

#### Tavily Provider

- [ ] Check for official MCP server availability
- [ ] Update with latest API parameters
- [ ] Add support for image inclusion in results
- [ ] Implement domain filtering capabilities

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
