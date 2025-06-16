# API Reference

Complete reference for all tools and endpoints available in MCP Search Hub.

## Table of Contents

- [Overview](#overview)
- [Core Search Tools](#core-search-tools)
- [Provider-Specific Tools](#provider-specific-tools)
- [Utility Tools](#utility-tools)
- [HTTP Endpoints](#http-endpoints)
- [Response Formats](#response-formats)
- [Error Handling](#error-handling)
- [Advanced Usage](#advanced-usage)

## Overview

MCP Search Hub provides two types of interfaces:

1. **MCP Tools**: For integration with MCP clients (Claude Desktop, Claude Code)
2. **HTTP API**: For direct HTTP requests and web integrations

All tools support both synchronous and asynchronous operations with comprehensive error handling and retry logic.

## Core Search Tools

### `search`

The main search tool that intelligently routes queries to the most appropriate provider(s).

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | ✅ | - | The search query text |
| `max_results` | integer | ❌ | 10 | Maximum number of results to return (1-50) |
| `advanced` | boolean | ❌ | false | Enable advanced search capabilities |
| `content_type` | string | ❌ | auto | Content type hint for better routing |
| `providers` | array | ❌ | auto | Explicit provider selection |
| `budget` | number | ❌ | 0.1 | Maximum cost budget in USD |
| `timeout_ms` | integer | ❌ | 5000 | Request timeout in milliseconds |

#### Content Type Hints

| Type | Description | Preferred Providers |
|------|-------------|-------------------|
| `FACTUAL` | Factual information, current events | Linkup, Perplexity |
| `ACADEMIC` | Research papers, scholarly content | Exa, Perplexity |
| `TECHNICAL` | Technical documentation, code | Exa, GitHub search |
| `NEWS` | Current news and events | Perplexity, Tavily |
| `COMMERCIAL` | Product information, reviews | Linkup, Tavily |
| `EDUCATIONAL` | Learning materials, tutorials | Exa, Firecrawl |

#### Example Usage

```python
# Basic search
result = client.invoke("search", {
    "query": "latest developments in quantum computing"
})

# Advanced search with constraints
result = client.invoke("search", {
    "query": "climate change research papers",
    "max_results": 20,
    "content_type": "ACADEMIC",
    "budget": 0.05,
    "advanced": true
})

# Provider-specific search
result = client.invoke("search", {
    "query": "startup funding news",
    "providers": ["perplexity", "linkup"],
    "content_type": "NEWS"
})
```

#### Response Format

```json
{
  "results": [
    {
      "title": "Result title",
      "url": "https://example.com",
      "snippet": "Result description...",
      "content": "Full content if available",
      "score": 0.95,
      "source": "provider_name",
      "published_date": "2024-01-15T10:30:00Z",
      "metadata": {
        "domain": "example.com",
        "content_type": "article",
        "estimated_reading_time": 5
      }
    }
  ],
  "query": "original query",
  "providers_used": ["linkup", "exa"],
  "total_results": 15,
  "total_cost": 0.023,
  "timing_ms": 1247,
  "cached": false
}
```

### `get_provider_info`

Get information about all available search providers.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `include_disabled` | boolean | ❌ | false | Include disabled providers in response |

#### Example Usage

```python
providers = client.invoke("get_provider_info")
```

#### Response Format

```json
{
  "providers": {
    "linkup": {
      "name": "Linkup",
      "enabled": true,
      "capabilities": ["web_search", "factual_queries"],
      "content_types": ["FACTUAL", "NEWS", "COMMERCIAL"],
      "accuracy_score": 0.91,
      "cost_per_request": 0.01,
      "timeout_ms": 10000
    }
  },
  "total_enabled": 4,
  "total_available": 5
}
```

## Provider-Specific Tools

All provider tools are automatically available through MCP Search Hub's embedded MCP servers.

### Firecrawl Tools

Advanced web scraping and content extraction tools.

#### `firecrawl_scrape`

Scrape content from a specific URL with advanced options.

```python
result = client.invoke("firecrawl_scrape", {
    "url": "https://example.com/article",
    "formats": ["markdown", "html"],
    "onlyMainContent": true,
    "waitFor": 2000
})
```

#### `firecrawl_search`

Search the web with content extraction capabilities.

```python
result = client.invoke("firecrawl_search", {
    "query": "AI research papers 2024",
    "limit": 10,
    "extract_depth": "advanced"
})
```

#### `firecrawl_crawl`

Start an asynchronous crawl job for comprehensive site analysis.

```python
job = client.invoke("firecrawl_crawl", {
    "url": "https://docs.example.com",
    "maxDepth": 3,
    "limit": 100,
    "scrapeOptions": {
        "formats": ["markdown"],
        "onlyMainContent": true
    }
})
```

#### `firecrawl_check_crawl_status`

Check the status of a crawl job.

```python
status = client.invoke("firecrawl_check_crawl_status", {
    "id": "crawl_job_id"
})
```

### Exa Tools

Semantic search and specialized content discovery.

#### `web_search_exa`

General web search with semantic understanding.

```python
result = client.invoke("web_search_exa", {
    "query": "machine learning model optimization",
    "numResults": 15
})
```

#### `research_paper_search`

Search academic papers and research content.

```python
papers = client.invoke("research_paper_search", {
    "query": "neural networks deep learning",
    "numResults": 20,
    "maxCharacters": 5000
})
```

#### `company_research`

Research companies and organizations.

```python
company_info = client.invoke("company_research", {
    "query": "anthropic.ai",
    "subpages": 15
})
```

#### `linkedin_search`

Search LinkedIn profiles and company pages.

```python
linkedin_results = client.invoke("linkedin_search", {
    "query": "anthropic company page",
    "numResults": 5
})
```

### Perplexity Tools

AI-powered search with reasoning capabilities.

#### `perplexity_ask`

Ask questions with AI-powered analysis.

```python
answer = client.invoke("perplexity_ask", {
    "query": "What are the latest developments in quantum computing?",
    "focus": "comprehensive"
})
```

#### `perplexity_research`

Conduct in-depth research on complex topics.

```python
research = client.invoke("perplexity_research", {
    "topic": "renewable energy trends 2024",
    "depth": "detailed"
})
```

### Linkup Tools

Premium content search with real-time results.

#### `linkup_search_web`

Search with configurable depth and result quality.

```python
results = client.invoke("linkup_search_web", {
    "query": "blockchain technology adoption",
    "depth": "deep"
})
```

### Tavily Tools

RAG-optimized search for retrieval applications.

#### `tavily_search`

Search optimized for RAG applications.

```python
results = client.invoke("tavily_search", {
    "query": "artificial intelligence ethics",
    "search_depth": "advanced",
    "max_results": 20
})
```

#### `tavily_extract`

Extract content from specific URLs.

```python
content = client.invoke("tavily_extract", {
    "urls": ["https://example.com/article1", "https://example.com/article2"],
    "extract_depth": "advanced"
})
```

## Utility Tools

### `health_check`

Check the health status of all providers and system components.

```python
health = client.invoke("health_check")
```

### `get_metrics`

Retrieve system performance metrics and statistics.

```python
metrics = client.invoke("get_metrics", {
    "include_provider_stats": true,
    "timeframe": "1h"
})
```

### `clear_cache`

Clear the query cache (requires admin privileges).

```python
result = client.invoke("clear_cache", {
    "cache_type": "all"  # Options: "memory", "redis", "all"
})
```

## HTTP Endpoints

For direct HTTP integration without MCP clients.

### POST `/search/combined`

Unified search endpoint equivalent to the `search` tool.

```bash
curl -X POST http://localhost:8000/search/combined \
  -H "Content-Type: application/json" \
  -d '{
    "query": "latest AI developments",
    "max_results": 10,
    "advanced": true
  }'
```

### GET `/health`

Health check endpoint for monitoring.

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "providers": {
    "linkup": "connected",
    "exa": "connected",
    "perplexity": "timeout"
  },
  "cache": "operational",
  "uptime": 3600
}
```

### GET `/metrics`

System metrics for monitoring and analytics.

```bash
curl http://localhost:8000/metrics
```

### GET `/providers`

List available providers and their status.

```bash
curl http://localhost:8000/providers
```

### POST `/providers/{provider_name}/search`

Search using a specific provider directly.

```bash
curl -X POST http://localhost:8000/providers/linkup/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "quantum computing news",
    "max_results": 5
  }'
```

## Response Formats

### Standard Response Structure

All API responses follow this structure:

```json
{
  "success": true,
  "data": {
    // Response data
  },
  "metadata": {
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_123456",
    "processing_time_ms": 1247
  }
}
```

### Error Response Structure

```json
{
  "success": false,
  "error": {
    "type": "ProviderTimeoutError",
    "message": "Search operation timed out",
    "details": {
      "provider": "exa",
      "timeout_ms": 5000
    },
    "request_id": "req_123456"
  }
}
```

### Search Result Structure

```json
{
  "title": "Article Title",
  "url": "https://example.com/article",
  "snippet": "Brief description...",
  "content": "Full article content (when available)",
  "score": 0.95,
  "source": "provider_name",
  "published_date": "2024-01-15T10:30:00Z",
  "metadata": {
    "domain": "example.com",
    "content_type": "article",
    "language": "en",
    "estimated_reading_time": 5,
    "author": "John Doe",
    "tags": ["AI", "technology"]
  }
}
```

## Error Handling

### Error Types

| Error Type | HTTP Status | Description | Retry |
|------------|-------------|-------------|--------|
| `ProviderTimeoutError` | 504 | Provider response timeout | ✅ |
| `ProviderRateLimitError` | 429 | Rate limit exceeded | ✅ |
| `ProviderAuthenticationError` | 401 | Invalid API key | ❌ |
| `QueryValidationError` | 400 | Invalid query parameters | ❌ |
| `BudgetExceededError` | 402 | Query budget exceeded | ❌ |
| `NoProvidersAvailableError` | 503 | All providers unavailable | ✅ |

### Handling Errors in Code

```python
try:
    result = client.invoke("search", {"query": "test"})
except Exception as e:
    if hasattr(e, 'error_type'):
        if e.error_type == 'ProviderRateLimitError':
            print(f"Rate limited, retry after {e.details.get('retry_after', 60)} seconds")
        elif e.error_type == 'BudgetExceededError':
            print(f"Budget exceeded: {e.details.get('cost_breakdown')}")
    else:
        print(f"Unexpected error: {e}")
```

## Advanced Usage

### Budget Management

Control spending with fine-grained budget constraints:

```python
# Set query-level budget
result = client.invoke("search", {
    "query": "expensive research query",
    "budget": 0.05,  # Max 5 cents
    "providers": ["linkup", "exa"]  # Exclude expensive providers
})

# Get cost breakdown
print(f"Total cost: ${result['total_cost']}")
print(f"Provider costs: {result['cost_breakdown']}")
```

### Performance Optimization

#### Caching Strategies

```python
# Force cache refresh
result = client.invoke("search", {
    "query": "time-sensitive query",
    "force_refresh": true
})

# Extend cache TTL for stable queries
result = client.invoke("search", {
    "query": "stable reference query",
    "cache_ttl": 3600  # Cache for 1 hour
})
```

#### Parallel Provider Execution

```python
# Execute multiple providers in parallel (default)
result = client.invoke("search", {
    "query": "comprehensive query",
    "providers": ["linkup", "exa", "perplexity"],
    "execution_strategy": "parallel"
})

# Use cascade strategy for cost optimization
result = client.invoke("search", {
    "query": "cost-sensitive query",
    "execution_strategy": "cascade",
    "cascade_threshold": 0.8  # Stop when confidence > 80%
})
```

### Content Type Optimization

Guide provider selection with content type hints:

```python
# Academic research
academic_results = client.invoke("search", {
    "query": "machine learning research",
    "content_type": "ACADEMIC",
    "max_results": 20
})

# Current news
news_results = client.invoke("search", {
    "query": "AI industry news",
    "content_type": "NEWS",
    "time_filter": "24h"
})

# Technical documentation
tech_results = client.invoke("search", {
    "query": "FastAPI documentation",
    "content_type": "TECHNICAL",
    "providers": ["exa"]  # Exa excels at technical content
})
```

### Batch Operations

Process multiple queries efficiently:

```python
# Batch search (if supported by client)
queries = [
    {"query": "AI research", "content_type": "ACADEMIC"},
    {"query": "tech news", "content_type": "NEWS"},
    {"query": "startup funding", "content_type": "COMMERCIAL"}
]

results = client.invoke("batch_search", {
    "queries": queries,
    "max_concurrent": 3
})
```

### Real-time Monitoring

Monitor search performance and costs:

```python
# Get real-time metrics
metrics = client.invoke("get_metrics", {
    "include_costs": true,
    "include_performance": true,
    "timeframe": "1h"
})

print(f"Total queries: {metrics['total_queries']}")
print(f"Total cost: ${metrics['total_cost']}")
print(f"Average response time: {metrics['avg_response_time']}ms")
print(f"Cache hit rate: {metrics['cache_hit_rate']:.1%}")
```

---

For more examples and integration patterns, see the [examples directory](examples/) in the repository.