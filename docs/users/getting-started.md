# Getting Started with MCP Search Hub

Welcome to MCP Search Hub! This guide will help you get up and running quickly with our intelligent multi-provider search aggregation server.

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Installation Methods](#installation-methods)
- [Configuration](#configuration)
- [First Search](#first-search)
- [Integration with Claude](#integration-with-claude)
- [Troubleshooting](#troubleshooting)
- [Next Steps](#next-steps)

## Quick Start

Get MCP Search Hub running in under 5 minutes:

```bash
# 1. Clone the repository
git clone https://github.com/BjornMelin/mcp-search-hub
cd mcp-search-hub

# 2. Install dependencies
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
uv pip install -r requirements.txt

# 3. Configure API keys (interactive setup)
python scripts/setup_claude_desktop.py

# 4. Start the server
python -m mcp_search_hub.main
```

That's it! Your search hub is now running and ready to use.

## Prerequisites

Before getting started, ensure you have:

### Required
- **Python 3.10+** (FastMCP 2.0 requirement)
- **API keys** for at least one search provider
- **Internet connection** for provider communication

### Optional
- **Docker** (for containerized deployment)
- **Node.js 16+** (for providers using Node.js MCP servers)
- **Redis** (for enhanced caching performance)

### Supported Platforms
- Linux (Ubuntu 20.04+, CentOS 8+)
- macOS (10.15+)
- Windows 10/11
- Windows Subsystem for Linux (WSL)

## Installation Methods

Choose the installation method that best fits your needs:

### Option 1: Interactive Setup (Recommended)

The interactive setup script guides you through the entire process:

```bash
git clone https://github.com/BjornMelin/mcp-search-hub
cd mcp-search-hub
python scripts/setup_claude_desktop.py
```

This script will:
- Check system requirements
- Install dependencies
- Guide you through API key configuration
- Set up Claude Desktop integration
- Validate your installation

### Option 2: Docker (Production Ready)

For production deployments or if you prefer containerization:

```bash
git clone https://github.com/BjornMelin/mcp-search-hub
cd mcp-search-hub

# Create .env file with your API keys
cp .env.example .env
# Edit .env with your configuration

# Run with Docker Compose
docker-compose up -d

# Verify it's running
curl http://localhost:8000/health
```

### Option 3: Manual Installation

For developers who want full control:

```bash
# 1. Clone and enter directory
git clone https://github.com/BjornMelin/mcp-search-hub
cd mcp-search-hub

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies (using uv for speed)
uv pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your API keys and preferences

# 5. Start the server
python -m mcp_search_hub.main
```

## Configuration

### Minimal Configuration

At minimum, you need API keys for the providers you want to use:

```bash
# Required: At least one provider API key
LINKUP_API_KEY=your_linkup_key
EXA_API_KEY=your_exa_key
PERPLEXITY_API_KEY=your_perplexity_key
TAVILY_API_KEY=your_tavily_key
FIRECRAWL_API_KEY=your_firecrawl_key
```

### Getting API Keys

Each provider offers free tiers or trials:

| Provider | Free Tier | Sign Up Link |
|----------|-----------|--------------|
| **Linkup** | 100 requests/month | [linkup.so](https://linkup.so) |
| **Exa** | 1,000 requests/month | [exa.ai](https://exa.ai) |
| **Perplexity** | $5 credit | [perplexity.ai](https://perplexity.ai) |
| **Tavily** | 1,000 requests/month | [tavily.com](https://tavily.com) |
| **Firecrawl** | 500 requests/month | [firecrawl.dev](https://firecrawl.dev) |

### Configuration File

Create a `.env` file in the project root:

```bash
# Server Configuration
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
TRANSPORT=http  # or "stdio" for Claude Desktop

# Provider API Keys
LINKUP_API_KEY=your_linkup_api_key
EXA_API_KEY=your_exa_api_key
PERPLEXITY_API_KEY=your_perplexity_api_key
TAVILY_API_KEY=your_tavily_api_key
FIRECRAWL_API_KEY=your_firecrawl_api_key

# Provider Settings (optional)
LINKUP_ENABLED=true
EXA_ENABLED=true
PERPLEXITY_ENABLED=true
TAVILY_ENABLED=true
FIRECRAWL_ENABLED=true

# Performance Settings
DEFAULT_BUDGET=0.1
CACHE_TTL=300
```

> 💡 **Tip**: You don't need all providers enabled. Start with 1-2 providers and add more as needed.

For detailed configuration options, see [Configuration Guide](../operators/configuration.md).

## First Search

Once your server is running, test it with a simple search:

### Using HTTP API

```bash
# Test the health endpoint
curl http://localhost:8000/health

# Perform a search
curl -X POST http://localhost:8000/search/combined \
  -H "Content-Type: application/json" \
  -d '{"query": "latest developments in artificial intelligence", "max_results": 5}'
```

### Using MCP Client

If you have an MCP client installed:

```python
from mcp.client import Client

client = Client("http://localhost:8000/mcp")
response = client.invoke("search", {
    "query": "latest developments in artificial intelligence",
    "max_results": 5
})
print(f"Found {len(response['results'])} results")
```

## Integration with Claude

MCP Search Hub is designed to work seamlessly with Claude Desktop and Claude Code.

### Claude Desktop Integration

1. **Automatic Setup** (recommended):
   ```bash
   python scripts/setup_claude_desktop.py
   ```

2. **Manual Setup**:
   Add to your Claude Desktop configuration:
   ```json
   {
     "mcpServers": {
       "mcp-search-hub": {
         "command": "python",
         "args": ["-m", "mcp_search_hub.main", "--transport", "stdio"],
         "env": {
           "LINKUP_API_KEY": "your_key_here",
           "EXA_API_KEY": "your_key_here"
         }
       }
     }
   }
   ```

3. **Restart Claude Desktop**

4. **Test the integration**:
   Ask Claude: *"What MCP tools do you have available?"*

### Claude Code Integration

For Claude Code CLI:

```bash
# Add to your Claude Code configuration
claude config mcp add mcp-search-hub python -m mcp_search_hub.main --transport stdio
```

## Troubleshooting

### Common Issues

**🔧 "Module not found" errors**
```bash
# Ensure you're in the virtual environment
source venv/bin/activate
# Reinstall dependencies
uv pip install -r requirements.txt
```

**🔧 "Permission denied" on port 8000**
```bash
# Use a different port
export PORT=8080
python -m mcp_search_hub.main
```

**🔧 "API key invalid" errors**
```bash
# Verify your API keys in .env
# Check provider status at their websites
# Try with a single provider first
```

**🔧 Docker container won't start**
```bash
# Check Docker logs
docker logs mcp-search-hub

# Verify .env file exists and has API keys
ls -la .env
```

### Getting Help

- **Documentation**: Check [Configuration Guide](../operators/configuration.md) and [API Reference](../developers/api-reference.md)
- **Issues**: Report bugs on [GitHub Issues](https://github.com/BjornMelin/mcp-search-hub/issues)
- **Logs**: Check server logs for detailed error information

### Health Checks

Verify your installation:

```bash
# Check server health
curl http://localhost:8000/health

# Check available providers
curl http://localhost:8000/providers

# Check metrics
curl http://localhost:8000/metrics
```

## Next Steps

Now that you have MCP Search Hub running:

1. **🔍 [Try Advanced Features](../developers/api-reference.md#advanced-usage)**
   - Provider-specific searches
   - Budget constraints
   - Content type hints

2. **⚙️ [Optimize Configuration](../operators/configuration.md)**
   - Rate limiting
   - Caching strategies
   - Performance tuning

3. **🚀 [Deploy to Production](docs/deployment.md)**
   - Docker production setup
   - Load balancing
   - Monitoring

4. **🛠️ [Contribute to Development](../developers/contributing.md)**
   - Development setup
   - Testing guidelines
   - Code contribution

5. **📚 [Explore Architecture](docs/architecture-overview.md)**
   - System design
   - Provider integration
   - Routing strategies

---

**Need help?** Join our community or check the [troubleshooting guide](docs/troubleshooting.md) for more detailed solutions.