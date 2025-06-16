# OpenAPI Documentation

MCP Search Hub provides comprehensive OpenAPI documentation to help developers understand and interact with the API.

## Accessing the Documentation

### Interactive API Documentation

The interactive API documentation is available at:

- **Swagger UI**: `/docs` - A user-friendly interface to explore and test the API endpoints
- **ReDoc**: `/redoc` - An alternative documentation UI with improved readability

### Schema Definition

The raw OpenAPI schema is available at:

- **OpenAPI JSON**: `/openapi.json` - The raw JSON schema definition
- **Downloadable Schema**: `/export-openapi` - The schema as a downloadable file

## API Endpoints

MCP Search Hub provides the following HTTP endpoints, all fully documented in the OpenAPI specification:

### Search Endpoints

- `POST /search/combined` - Execute a combined search across multiple providers

### Monitoring Endpoints

- `GET /health` - Check server health status
- `GET /metrics` - Get server performance metrics

### Documentation Endpoints

- `GET /docs` - Swagger UI interactive API documentation
- `GET /redoc` - ReDoc interactive API documentation
- `GET /openapi.json` - Raw OpenAPI schema
- `GET /export-openapi` - Downloadable OpenAPI schema

## MCP Tools

The MCP Search Hub server also provides MCP tools that can be used with MCP clients. These tools are also documented in the OpenAPI specification:

### Unified Search Tool

- `search` - Search across multiple providers with intelligent routing

### Provider-Specific Tools

MCP Search Hub dynamically registers tools from the embedded provider MCP servers. These typically include:

- **Firecrawl Tools**: Tools like `firecrawl_search`, `firecrawl_scrape`, `firecrawl_map`, etc.
- **Exa Tools**: Tools like `exa_search`, `exa_research_papers`, etc.
- **Perplexity Tools**: Tools like `perplexity_ask`, `perplexity_research`, etc.
- **Tavily Tools**: Tools like `tavily_search`, `tavily_extract`, etc.
- **Linkup Tools**: Tools like `linkup_search_web`, etc.

## Client SDK Generation

MCP Search Hub provides a script to generate client SDKs for various programming languages using the OpenAPI Generator. The script is available at `scripts/generate_client_sdk.py`.

### Prerequisites

- Java must be installed
- OpenAPI Generator CLI must be installed

### Usage

```bash
# Generate client SDKs for Python, TypeScript, Go, and Java
python scripts/generate_client_sdk.py

# Generate client SDK for a specific language
python scripts/generate_client_sdk.py --languages python

# Specify the OpenAPI schema URL
python scripts/generate_client_sdk.py --url http://localhost:8000/openapi.json

# Specify the output directory
python scripts/generate_client_sdk.py --output-dir ./my-clients
```

### Generated SDKs

The script will generate client SDKs in the specified output directory:

```
./clients/
  ├── python/
  ├── typescript-fetch/
  ├── go/
  └── java/
```

## Using the Client SDKs

### Python Client

```python
from mcp_search_hub_client import ApiClient, Configuration
from mcp_search_hub_client.api import DefaultApi

# Configure the API client
config = Configuration(host="http://localhost:8000")
client = ApiClient(config)
api = DefaultApi(client)

# Perform a search
response = api.search_combined_post({
    "query": "latest advancements in artificial intelligence",
    "max_results": 5
})

# Process the results
for result in response.results:
    print(f"Title: {result.title}")
    print(f"URL: {result.url}")
    print(f"Snippet: {result.snippet}")
    print(f"Source: {result.source}")
    print("-" * 50)
```

### TypeScript Client

```typescript
import { DefaultApi, Configuration } from 'mcp-search-hub-client';

// Configure the API client
const config = new Configuration({
    basePath: 'http://localhost:8000',
});
const api = new DefaultApi(config);

// Perform a search
api.searchCombinedPost({
    query: 'latest advancements in artificial intelligence',
    maxResults: 5
}).then(response => {
    // Process the results
    response.results.forEach(result => {
        console.log(`Title: ${result.title}`);
        console.log(`URL: ${result.url}`);
        console.log(`Snippet: ${result.snippet}`);
        console.log(`Source: ${result.source}`);
        console.log('-'.repeat(50));
    });
}).catch(error => {
    console.error('Error performing search:', error);
});
```

## Security

The API can be secured using API keys. When the authentication middleware is enabled, requests to the API must include the `X-API-Key` header with a valid API key.

```
X-API-Key: your-api-key
```

This authentication requirement is documented in the OpenAPI schema.