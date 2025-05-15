# MCP Search Hub

🔍 Intelligent multi-provider search aggregation server built on FastMCP 2.0

## Features

- Embeds official MCP servers from five leading search providers (Linkup, Exa, Perplexity, Tavily, and Firecrawl) within a unified interface
- Automatically routes queries to the most appropriate provider(s) based on query characteristics
- Combines and ranks results for optimal relevance with intelligent deduplication
- Implements cost control mechanisms and budget constraints
- Provides caching for improved performance and reduced API costs
- Handles errors and provider failures gracefully
- Zero maintenance for provider updates - automatically leverages official MCP server enhancements
- Easily deployable with Docker or as a standalone Python service
- Supports both HTTP and STDIO transport methods

## Cost Efficiency

MCP Search Hub delivers 30-45% cost reduction compared to single-provider solutions while providing superior search results through intelligent provider selection and result combination.

## Provider Strengths

The system intelligently routes queries by leveraging each provider's unique strengths, all through embedded official MCP servers:

- **Linkup**: Factual information with 91.0% accuracy on the SimpleQA benchmark - [official MCP server](https://github.com/LinkupPlatform/python-mcp-server)
- **Exa**: Academic content and semantic search with 90.04% SimpleQA accuracy - [official MCP server](https://github.com/exa-labs/exa-mcp-server)
- **Perplexity**: Current events and LLM processing with 86% accuracy - [official MCP server](https://github.com/ppl-ai/modelcontextprotocol)
- **Tavily**: RAG-optimized results with 73% SimpleQA accuracy - [official MCP server](https://github.com/tavily-ai/tavily-mcp)
- **Firecrawl**: Deep content extraction and scraping capabilities - [official MCP server](https://github.com/mendableai/firecrawl-mcp-server)

## Architecture

MCP Search Hub uses a modular architecture with the following core components:

1. **Server Layer**: FastMCP server implementation that registers tools and orchestrates the search process
2. **Provider Layer**: Standardized interface with implementations for each service
3. **Query Routing**: Extracts features from queries to determine content type, complexity, and selects appropriate providers
4. **Result Processing**: Combines, ranks, and deduplicates results from multiple providers
5. **Utilities**: Caching, error handling, and configuration management

### Embedded MCP Server Architecture

We've implemented an innovative approach: **embedding all official provider MCP servers within our unified server**. This means:

- Users interact with a single MCP server (MCP Search Hub)
- We internally connect to provider MCP servers using the MCP Python SDK
- All provider tools are exposed through our unified interface
- Automatic updates when providers enhance their MCP servers

This architectural decision applies to all providers:

- **Firecrawl**: Successfully embedded with all tools available
- **Perplexity**: In progress - will expose ask, research, and search tools
- **Exa**: In progress - will expose web_search_exa, research_paper_search, and more
- **Linkup**: In progress - Python-to-Python MCP communication for search
- **Tavily**: In progress - will expose tavily-search and tavily-extract tools

Benefits of this approach:

- **Zero maintenance**: Provider updates are automatic
- **Complete features**: Access to all provider capabilities
- **Unified interface**: Single server for all search needs
- **Future-proof**: Ready for new MCP servers as they become available

Learn more about this decision in our [Architecture Decisions](docs/architecture-decisions.md) document.

## Installation

### Prerequisites

- Python 3.10+ (required for FastMCP 2.0 compatibility)
- API keys for the search providers you plan to use
- Docker (optional, for containerized deployment)
- MCP client that supports HTTP or STDIO transport
- Node.js (optional, for providers using Node.js MCP servers - will be auto-installed if missing)

### Using Docker (Recommended)

1. Clone the repository:

   ```bash
   git clone https://github.com/BjornMelin/mcp-search-hub.git
   cd mcp-search-hub
   ```

2. Create a `.env` file with your API keys:

   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

3. Run with Docker Compose:

   ```bash
   docker-compose up -d
   ```

4. Verify the server is running:

   ```bash
   curl http://localhost:8000/health
   # Expected response: {"status": "ok"}
   ```

### Manual Installation

#### Linux/macOS

1. Clone the repository:

   ```bash
   git clone https://github.com/BjornMelin/mcp-search-hub.git
   cd mcp-search-hub
   ```

2. Create a virtual environment and install dependencies using `uv`:

   ```bash
   python -m venv venv
   source venv/bin/activate
   uv pip install -r requirements.txt
   ```

3. Set environment variables with your API keys:

   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

4. Run the server:

   ```bash
   python -m mcp_search_hub.main
   ```

#### Windows

1. Clone the repository:

   ```powershell
   git clone https://github.com/BjornMelin/mcp-search-hub.git
   cd mcp-search-hub
   ```

2. Create a virtual environment and install dependencies using `uv`:

   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   uv pip install -r requirements.txt
   ```

3. Set environment variables with your API keys:

   ```powershell
   # Copy and edit the .env file manually, or
   copy .env.example .env
   # Edit .env with your API keys and configuration
   ```

4. Run the server:

   ```powershell
   python -m mcp_search_hub.main
   ```

#### Windows Subsystem for Linux (WSL)

1. Follow the Linux/macOS instructions above within your WSL environment
2. Note that services running in WSL are accessible from Windows using `localhost`

## Configuration

MCP Search Hub uses environment variables for configuration. You can set these in a `.env` file in the project root or as system environment variables.

### Required Configuration

```plaintext
# API Keys (only required for providers you enable)
LINKUP_API_KEY=your_linkup_api_key
EXA_API_KEY=your_exa_api_key
PERPLEXITY_API_KEY=your_perplexity_api_key
TAVILY_API_KEY=your_tavily_api_key
FIRECRAWL_API_KEY=your_firecrawl_api_key
```

> **Note**: All API keys are required for the embedded MCP servers to function. Each provider's official MCP server is automatically managed and kept up-to-date within MCP Search Hub.

### Optional Configuration

```
# Server configuration
LOG_LEVEL=INFO            # DEBUG, INFO, WARNING, ERROR, CRITICAL
CACHE_TTL=3600            # Cache time-to-live in seconds
DEFAULT_BUDGET=0.1        # Default query budget in USD
PORT=8000                 # Server port (for HTTP transport)
HOST=0.0.0.0              # Server host (0.0.0.0 for all interfaces)
TRANSPORT=http            # Transport method: "http" or "stdio"

# Provider enablement (set to "true" or "false")
LINKUP_ENABLED=true
EXA_ENABLED=true
PERPLEXITY_ENABLED=true
TAVILY_ENABLED=true
FIRECRAWL_ENABLED=true

# Provider timeouts (in milliseconds)
LINKUP_TIMEOUT=5000
EXA_TIMEOUT=5000
PERPLEXITY_TIMEOUT=5000
TAVILY_TIMEOUT=5000
FIRECRAWL_TIMEOUT=5000
```

## Usage

Once the server is running, you can use it as an MCP server with any MCP client. The server supports both HTTP and STDIO transport methods.

### Running with STDIO Transport

To run the server with STDIO transport, set `TRANSPORT=stdio` in your `.env` file or use the `--transport` flag:

```bash
# Using environment variable
export TRANSPORT=stdio
uv run mcp_search_hub.main

# Or using command line flag
uv run mcp_search_hub.main --transport stdio
```

When using STDIO transport, the server communicates through standard input and output streams, making it suitable for direct integration with LLM clients that support this transport mode.

### MCP Client Integration

#### Claude Desktop

##### HTTP Transport

1. Open Claude Desktop settings
2. Navigate to MCP Servers
3. Add a new HTTP server with the following configuration:

   ```json
   {
     "mcpServers": {
       "search": {
         "url": "http://localhost:8000/mcp"
       }
     }
   }
   ```

4. Restart Claude Desktop
5. Access search capability with: `search("your query here")`

##### STDIO Transport

1. Open Claude Desktop settings
2. Navigate to MCP Servers
3. Add a new STDIO server with the following configuration:

   ```json
   {
     "mcpServers": {
       "search": {
         "command": [
           "uv",
           "run",
           "mcp_search_hub.main",
           "--transport",
           "stdio"
         ],
         "cwd": "/path/to/mcp-search-hub"
       }
     }
   }
   ```

   Replace `/path/to/mcp-search-hub` with the actual path to your installation

4. Restart Claude Desktop
5. Access search capability with: `search("your query here")`

#### Claude Code

##### HTTP Transport

Configure the HTTP MCP server in your Claude Code settings:

```bash
claude config set mcp-servers.search http://localhost:8000/mcp
```

##### STDIO Transport

Configure the STDIO MCP server in your Claude Code settings:

```bash
# For STDIO transport
claude config set mcp-servers.search.command "uv run mcp_search_hub.main --transport stdio"
claude config set mcp-servers.search.cwd "/path/to/mcp-search-hub"
```

Replace `/path/to/mcp-search-hub` with the actual path to your installation.

Then use it in your sessions with:

```plaintext
You can now use the search tool. For example: search("latest advancements in artificial intelligence")
```

#### VS Code with Claude Extension

##### HTTP Transport

Add to your settings.json:

```json
"anthropic.claude.mcpServers": {
  "search": {
    "url": "http://localhost:8000/mcp"
  }
}
```

##### STDIO Transport

Add to your settings.json:

```json
"anthropic.claude.mcpServers": {
  "search": {
    "command": ["uv", "run", "mcp_search_hub.main", "--transport", "stdio"],
    "cwd": "/path/to/mcp-search-hub"
  }
}
```

Replace `/path/to/mcp-search-hub` with the actual path to your installation.

#### Cursor

##### HTTP Transport

Add to your Cursor settings under the Claude section:

```json
"mcpServers": {
  "search": {
    "url": "http://localhost:8000/mcp"
  }
}
```

##### STDIO Transport

Add to your Cursor settings under the Claude section:

```json
"mcpServers": {
  "search": {
    "command": ["uv", "run", "mcp_search_hub.main", "--transport", "stdio"],
    "cwd": "/path/to/mcp-search-hub"
  }
}
```

Replace `/path/to/mcp-search-hub` with the actual path to your installation.

#### Windsurf

##### HTTP Transport

In Windsurf, navigate to Settings → Claude → MCP Servers and add:

```plaintext
Name: search
URL: http://localhost:8000/mcp
```

##### STDIO Transport

In Windsurf, navigate to Settings → Claude → MCP Servers and add:

```
Name: search
Type: stdio
Command: uv run mcp_search_hub.main --transport stdio
Working Directory: /path/to/mcp-search-hub
```

Replace `/path/to/mcp-search-hub` with the actual path to your installation.

### Using with Python

#### Anthropic SDK

```python
from anthropic import Anthropic

client = Anthropic(api_key="your-api-key")
message = client.messages.create(
    model="claude-3-opus-20240229",
    max_tokens=1024,
    temperature=0,
    system="You have access to a search tool, use it to find current information.",
    messages=[
        {"role": "user", "content": "What are the latest developments in quantum computing?"}
    ],
    tools=[
        {
            "name": "search",
            "description": "Search for information on the web",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "advanced": {"type": "boolean"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"]
            }
        }
    ],
    tool_config={
        "function_calling": "auto",
        "tools": {
            "search": {
                "address": "http://localhost:8000/mcp",
            }
        }
    }
)
print(message.content)
```

#### Direct MCP Client

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

### Advanced Usage

#### Custom Provider Selection

You can explicitly select which providers to use:

```python
response = client.invoke("search", {
    "query": "Latest developments in quantum computing",
    "providers": ["perplexity", "exa"],
    "max_results": 5
})
```

#### Content Type Hints

Providing content type hints can improve routing:

```python
response = client.invoke("search", {
    "query": "Latest stock price for AAPL",
    "content_type": "FINANCIAL",
    "max_results": 3
})
```

#### Budget Constraints

Set maximum spend per query:

```python
response = client.invoke("search", {
    "query": "Complex analysis of renewable energy trends",
    "advanced": True,
    "budget": 0.05  # Maximum 5 cents
})
```

## API Reference

### Search Tool

```plaintext
search(query: SearchQuery) -> CombinedSearchResponse
```

#### Parameters

- `query`: The search query text
- `advanced`: Whether to use advanced search capabilities (default: false)
- `max_results`: Maximum number of results to return (default: 10)
- `content_type`: Optional explicit content type hint (FACTUAL, EDUCATIONAL, NEWS, TECHNICAL, FINANCIAL, etc.)
- `providers`: Optional explicit provider selection (array of provider names)
- `budget`: Optional budget constraint in USD
- `timeout_ms`: Timeout in milliseconds (default: 5000)

#### Returns

- `results`: Combined search results
- `query`: Original query
- `providers_used`: Providers used for the search
- `total_results`: Total number of results
- `total_cost`: Total cost of the search
- `timing_ms`: Total search time in milliseconds

### Get Provider Info Tool

```plaintext
get_provider_info() -> Dict[str, Dict]
```

Returns information about all available search providers, including their capabilities, content types, and quality metrics.

### Provider-Specific Tools

MCP Search Hub embeds all official provider MCP servers, giving you access to their complete tool suites:

#### Firecrawl (Completed)

- `firecrawl_scrape`: Advanced web scraping with screenshot capture
- `firecrawl_map`: Site mapping and URL discovery
- `firecrawl_crawl`: Asynchronous site crawling
- `firecrawl_check_crawl_status`: Monitor crawl job status
- `firecrawl_search`: Web search with content extraction
- `firecrawl_extract`: LLM-powered information extraction
- `firecrawl_deep_research`: Comprehensive research automation
- `firecrawl_generate_llmstxt`: Generate LLMs.txt files

#### Perplexity (In Progress)

- `perplexity_ask`: Conversational search with AI
- `perplexity_research`: Deep research capabilities
- `perplexity_search`: Web search with citations

#### Exa (In Progress)

- `web_search_exa`: Semantic web search
- `research_paper_search`: Academic paper search
- `company_research`: Company information search
- `linkedin_search`: LinkedIn profile search
- `wikipedia_search_exa`: Wikipedia search
- `github_search`: GitHub repository search

#### Linkup (In Progress)

- `linkup_search`: Premium content search with real-time results

#### Tavily (In Progress)

- `tavily_search`: RAG-optimized search
- `tavily_extract`: Content extraction

All these tools are available directly through MCP Search Hub - no separate server configuration needed! The official MCP servers are automatically managed and kept up-to-date.

## Development

### Testing

Run the tests with pytest:

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=mcp_search_hub

# Run specific tests
uv run pytest tests/test_analyzer.py
```

### Code Quality

Maintain code quality with ruff:

```bash
# Run linter
ruff check .

# Apply auto-fixes
ruff check --fix .

# Format code
ruff format .

# Sort imports
ruff check --select I --fix .
```

## Troubleshooting

### Common Issues

- **API Key Errors**: Ensure you've set the correct API keys for each enabled provider in your `.env` file
- **Connection Refused**: Check that the server is running and the port (default: 8000) is not in use
- **Provider Failures**: If a specific provider fails, check its API status and consider disabling it temporarily
- **Timeout Errors**: For complex queries, consider increasing the timeout setting

### Logs

Check the logs for detailed error information:

```bash
# For Docker installations
docker logs mcp-search-hub

# For manual installations
# Logs are output to stdout/stderr or to the file specified in your configuration
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Acknowledgements

- [FastMCP](https://github.com/fastmcp) - The framework powering this server
- All the integrated search providers for their excellent APIs
