# Quick Start Tutorial

This tutorial will get you searching with MCP Search Hub in under 5 minutes.

## Prerequisites

- Docker installed on your system
- At least one API key from a supported provider (Linkup, Exa, Perplexity, Tavily, or Firecrawl)

## Step 1: Create Your Configuration

Create a `.env` file with your API keys:

```bash
# At least one provider API key is required
LINKUP_API_KEY=your_linkup_key_here
EXA_API_KEY=your_exa_key_here
PERPLEXITY_API_KEY=your_perplexity_key_here
TAVILY_API_KEY=your_tavily_key_here
FIRECRAWL_API_KEY=your_firecrawl_key_here
```

## Step 2: Start MCP Search Hub

Run with Docker:

```bash
docker run -d \
  --name mcp-search-hub \
  -p 8000:8000 \
  --env-file .env \
  mcp-search-hub:latest
```

## Step 3: Verify It's Running

Check the health endpoint:

```bash
curl http://localhost:8000/health
```

You should see a response showing which providers are active.

## Step 4: Your First Search

### Using the Search Tool

The primary way to search is through the unified `search` tool:

```bash
curl -X POST http://localhost:8000/search/combined \
  -H "Content-Type: application/json" \
  -d '{
    "query": "latest developments in quantum computing",
    "max_results": 10
  }'
```

### Response Structure

You'll receive a response with:
- **results**: Array of search results from multiple providers
- **metadata**: Information about the search execution

```json
{
  "results": [
    {
      "title": "Quantum Computing Breakthrough...",
      "url": "https://example.com/article",
      "snippet": "Researchers have achieved...",
      "provider": "exa",
      "score": 0.95
    }
    // ... more results
  ],
  "metadata": {
    "request_id": "uuid",
    "providers_used": ["exa", "linkup"],
    "result_count": 10,
    "response_time": 1.23
  }
}
```

## Step 5: Advanced Search Options

### Search with Raw Content

Get full content from web pages:

```bash
curl -X POST http://localhost:8000/search/combined \
  -H "Content-Type: application/json" \
  -d '{
    "query": "climate change solutions",
    "max_results": 5,
    "raw_content": true
  }'
```

### Provider-Specific Search

Use provider-specific tools for specialized searches:

```bash
# Research papers with Exa
curl -X POST http://localhost:8000/tools/exa_research_papers \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning optimization",
    "numResults": 10
  }'
```

## Next Steps

- **Configure More Providers**: Add more API keys to search across additional sources
- **Explore Provider Tools**: Each provider offers specialized search capabilities
- **Set Up Claude Desktop**: Integrate with Claude for conversational search
- **Learn Advanced Features**: Explore routing, caching, and optimization

## Common Issues

### No Results Returned
- Verify your API keys are correct
- Check provider status at `/health`
- Ensure your query is well-formed

### Slow Response Times
- Some providers may be slower than others
- Consider adjusting timeout settings
- Use caching for repeated queries

### Provider Errors
- Check provider-specific rate limits
- Verify API key permissions
- See provider documentation for error codes

## Getting Help

- Check the [FAQ](/docs/users/faq.md)
- Review [troubleshooting guide](/docs/troubleshooting/common-issues.md)
- Ask in [discussions](https://github.com/yourusername/mcp-search-hub/discussions)