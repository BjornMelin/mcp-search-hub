# MCP Search Hub

🔍 Intelligent multi-provider search aggregation server built on FastMCP 2.0

## Features

- Integrates five leading search providers (Linkup, Exa, Perplexity, Tavily, and Firecrawl) with unified API
- Automatically routes queries to the most appropriate provider(s)
- Combines and ranks results for optimal relevance
- Implements cost control mechanisms
- Provides caching for improved performance
- Handles errors and failures gracefully
- Easily deployable with Docker

## Cost Efficiency

MCP Search Hub delivers 30-45% cost reduction compared to single-provider solutions while providing superior search results through intelligent provider selection and result combination.

## Provider Strengths

The system leverages each provider's strengths:
- **Linkup**: Factual information with 91.0% accuracy on the SimpleQA benchmark
- **Exa**: Academic content and semantic search with 90.04% SimpleQA accuracy
- **Perplexity**: Current events and LLM processing with 86% accuracy
- **Tavily**: RAG-optimized results with 73% SimpleQA accuracy
- **Firecrawl**: Deep content extraction and scraping

## Installation

### Using Docker

1. Clone the repository:
   ```
   git clone https://github.com/BjornMelin/mcp-search-hub.git
   cd mcp-search-hub
   ```

2. Create a `.env` file with your API keys (see `.env.example`):
   ```
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. Run with Docker Compose:
   ```
   docker-compose up -d
   ```

### Manual Installation

1. Clone the repository:
   ```
   git clone https://github.com/BjornMelin/mcp-search-hub.git
   cd mcp-search-hub
   ```

2. Create a virtual environment and install dependencies:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Set environment variables with your API keys (see `.env.example`).

4. Run the server:
   ```
   python -m mcp_search_hub.main
   ```

## Usage

Once the server is running, you can use it as an MCP server with any MCP client, including:

- Claude Desktop
- Anthropic SDK
- LangChain
- Custom applications

### Example: Using with Claude Desktop

Add the server to your Claude Configuration:

```json
{
  "mcpServers": {
    "search": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Example: Using with Python

```python
from mcp.client import Client

# Connect to the server
client = Client("http://localhost:8000/mcp")

# Search with automatic provider selection
response = client.invoke("search", {
    "query": "Latest developments in quantum computing",
    "advanced": True,
    "max_results": 5
})

# Print results
for result in response["results"]:
    print(f"Title: {result['title']}")
    print(f"URL: {result['url']}")
    print(f"Snippet: {result['snippet']}")
    print(f"Source: {result['source']}")
    print("-" * 50)
```

## API Reference

### Search Tool

```
search(query: SearchQuery) -> CombinedSearchResponse
```

#### Parameters:
- `query`: The search query text
- `advanced`: Whether to use advanced search capabilities (default: false)
- `max_results`: Maximum number of results to return (default: 10)
- `content_type`: Optional explicit content type hint
- `providers`: Optional explicit provider selection
- `budget`: Optional budget constraint in USD
- `timeout_ms`: Timeout in milliseconds (default: 5000)

#### Returns:
- `results`: Combined search results
- `query`: Original query
- `providers_used`: Providers used for the search
- `total_results`: Total number of results
- `total_cost`: Total cost of the search
- `timing_ms`: Total search time in milliseconds

### Get Provider Info Tool

```
get_provider_info() -> Dict[str, Dict]
```

Returns information about all available search providers, including their capabilities, content types, and quality metrics.

## License

This project is licensed under the MIT License - see the LICENSE file for details.