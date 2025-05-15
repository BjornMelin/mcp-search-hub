# MCP Search Hub TODO List

## Core Functionality

- [ ] Implement stdin/stdout transport option for command-line usage
  - [ ] Add transport parameter to main.py with choice between "streamable-http" and "stdio"
  - [ ] Implement stdio transport handling in FastMCP server initialization
  - [ ] Update shutdown handler for stdio transport
  - [ ] Add CLI argument parser to support transport options and API keys

- [ ] Add support for returning raw content from providers when requested
  - [ ] Update SearchQuery model to add raw_content: bool parameter 
  - [ ] Modify provider implementations to include full content when raw_content=True
  - [ ] Update result processing to handle raw content appropriately

- [ ] Add health check and metrics endpoints
  - [ ] Implement health check route using @mcp.custom_route("/health")
  - [ ] Create metrics endpoint for tracking usage statistics
  - [ ] Add provider status checks to health endpoint

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

### Strategy Options

#### Option 1: Refactor to use official provider MCP servers
- [ ] Research how to integrate with official provider MCP servers
- [ ] Update architecture to use official MCP servers as fallbacks
- [ ] Implement proxy mode to route requests to provider-specific MCP servers

#### Option 2: Update existing provider implementations
- [ ] Update all providers with latest API interfaces and capabilities
- [ ] Enhance error handling and retry logic across all providers
- [ ] Implement advanced features for each provider

### Exa Provider
- [ ] Update to Exa API v2
  - [ ] Add support for time range filtering
  - [ ] Implement highlight extraction
  - [ ] Update response parsing to support new result fields
- [ ] Add specialized Exa tools (research_paper_search, company_research)
- [ ] Implement content extraction capability

### Linkup Provider
- [ ] Update to handle advanced output formats (aggregated, curated)
- [ ] Add support for domain filtering (allowed/blocked domains)
- [ ] Implement request chunking for deep searches
- [ ] Add LinkedIn-specific search capabilities

### Perplexity Provider
- [ ] Update with latest API model options (including "sonar-pro" model)
- [ ] Add support for perplexity_research capability
- [ ] Add perplexity_reason capability for reasoning tasks
- [ ] Implement conversation history tracking

### Tavily Provider
- [ ] Update with latest API parameters
- [ ] Add support for image inclusion in results
- [ ] Implement domain filtering capabilities
- [ ] Add support for topic-specific search configurations

### Firecrawl Provider
- [ ] Implement full tool suite
  - [ ] Add firecrawl_map for URL discovery
  - [ ] Implement firecrawl_crawl for async site crawling
  - [ ] Add firecrawl_extract for structured data extraction
  - [ ] Implement firecrawl_deep_research capability
- [ ] Add support for generating LLMs.txt for website context
- [ ] Improve URL extraction and content handling

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

- [ ] Improve documentation
  - [ ] Create README.md with installation and usage instructions
  - [ ] Add configuration guide for different environments
  - [ ] Create example configurations for MCP clients
  - [ ] Document provider-specific features and limitations

## MCP Client Integration

- [ ] Create client setup instructions for various MCP clients
  - [ ] Add Claude Desktop configuration guide
  - [ ] Create Claude Code integration instructions
  - [ ] Add VS Code client configuration
  - [ ] Document Cursor and Windsurf integration

- [ ] Add platform-specific installation instructions
  - [ ] Create Windows installation guide
  - [ ] Add WSL on Windows setup instructions
  - [ ] Document macOS installation process
  - [ ] Add Docker deployment guide

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