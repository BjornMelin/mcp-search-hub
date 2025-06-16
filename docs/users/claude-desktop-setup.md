# Claude Desktop Setup Guide

This guide provides complete instructions for integrating MCP Search Hub with Claude Desktop, enabling you to use 35+ search tools from 5 providers (Tavily, Exa, Linkup, Firecrawl, Perplexity) directly within Claude Desktop.

## Quick Start (5 Steps)

### 1. Install MCP Search Hub

```bash
# Clone and install
git clone https://github.com/BjornMelin/mcp-search-hub
cd mcp-search-hub
uv pip install -r requirements.txt

# Verify installation
python -m mcp_search_hub.main --help
```

### 2. Get API Keys

Obtain API keys from the providers you want to use:

- **Tavily**: [Get API Key](https://tavily.com/) (Required for web search)
- **Exa**: [Get API Key](https://exa.ai/) (Required for research and competitor analysis)  
- **Linkup**: [Get API Key](https://linkup.ai/) (Required for deep web search)
- **Firecrawl**: [Get API Key](https://firecrawl.dev/) (Required for web scraping/crawling)
- **Perplexity**: [Get API Key](https://perplexity.ai/) (Required for AI-powered research)

### 3. Locate Claude Desktop Config File

Find your Claude Desktop configuration file based on your operating system:

**macOS**:
```bash
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Windows**:
```bash
%APPDATA%\Claude\config\claude_desktop_config.json
```

**Linux**:
```bash
~/.config/Claude/config/claude_desktop_config.json
```

### 4. Configure Claude Desktop

Add the following configuration to your `claude_desktop_config.json` file:

```json
{
  "mcpServers": {
    "mcp-search-hub": {
      "command": "python",
      "args": [
        "-m", 
        "mcp_search_hub.main", 
        "--transport", 
        "stdio"
      ],
      "env": {
        "TAVILY_API_KEY": "tvly-your-api-key-here",
        "EXA_API_KEY": "exa-your-api-key-here",
        "LINKUP_API_KEY": "lp-your-api-key-here",
        "FIRECRAWL_API_KEY": "fc-your-api-key-here",
        "PERPLEXITY_API_KEY": "pplx-your-api-key-here",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

**Important**: Replace the placeholder API keys with your actual keys from step 2.

### 5. Restart Claude Desktop

Close and restart Claude Desktop completely for the configuration to take effect.

## Verification

After restart, verify the setup is working:

1. **Check Available Tools**: In a new Claude Desktop conversation, ask:
   ```
   What MCP tools do you have available?
   ```

2. **Test Search**: Try a search query:
   ```
   Can you search for recent developments in AI using the search tools?
   ```

3. **Test Specific Providers**: Test individual provider tools:
   ```
   Use Firecrawl to scrape the homepage of example.com
   Use Exa to find competitors for OpenAI
   Use Tavily to search for recent news about climate change
   ```

## Available Tools and Capabilities

Once configured, you'll have access to 35+ tools across 5 providers:

### 🔍 Unified Search Tools
- `search`: Multi-provider intelligent search with automatic provider selection
- `get_provider_info`: View provider status and capabilities

### 🌐 Tavily (Web Search & Extraction)
- `tavily_search`: Advanced web search with configurable depth
- `tavily_extract`: Extract content from specific URLs

### 🧠 Exa (Research & Analysis)  
- `exa_search`: Neural web search
- `exa_research_papers`: Find academic papers
- `exa_company_research`: Research companies
- `exa_competitor_finder`: Find competitors
- `exa_linkedin_search`: Search LinkedIn
- `exa_wikipedia_search`: Search Wikipedia
- `exa_github_search`: Search GitHub repositories
- `exa_crawl`: Crawl and extract content

### 🔗 Linkup (Deep Web Search)
- `linkup_search_web`: Deep web search with standard/deep modes

### 🕷️ Firecrawl (Web Scraping & Crawling)
- `firecrawl_scrape`: Scrape content from URLs
- `firecrawl_map`: Discover URLs from a starting point
- `firecrawl_crawl`: Start asynchronous crawls
- `firecrawl_check_crawl_status`: Monitor crawl progress
- `firecrawl_search`: Search and scrape simultaneously
- `firecrawl_extract`: Extract structured data
- `firecrawl_deep_research`: Conduct comprehensive research
- `firecrawl_generate_llmstxt`: Generate LLMs.txt files

### 🤖 Perplexity (AI Research)
- `perplexity_ask`: AI-powered question answering
- `perplexity_research`: Deep research with citations
- `perplexity_reason`: Advanced reasoning tasks

## Configuration Options

### Minimal Configuration (Essential Providers Only)

If you only want to use specific providers, you can configure a subset:

```json
{
  "mcpServers": {
    "mcp-search-hub": {
      "command": "python",
      "args": ["-m", "mcp_search_hub.main", "--transport", "stdio"],
      "env": {
        "TAVILY_API_KEY": "tvly-your-api-key-here",
        "EXA_API_KEY": "exa-your-api-key-here",
        "LINKUP_API_KEY": "lp-your-api-key-here",
        "FIRECRAWL_ENABLED": "false",
        "PERPLEXITY_ENABLED": "false"
      }
    }
  }
}
```

### Advanced Configuration

For advanced users, additional environment variables are available:

```json
{
  "mcpServers": {
    "mcp-search-hub": {
      "command": "python",
      "args": ["-m", "mcp_search_hub.main", "--transport", "stdio"],
      "env": {
        "TAVILY_API_KEY": "tvly-your-api-key-here",
        "EXA_API_KEY": "exa-your-api-key-here",
        "LINKUP_API_KEY": "lp-your-api-key-here",
        "FIRECRAWL_API_KEY": "fc-your-api-key-here",
        "PERPLEXITY_API_KEY": "pplx-your-api-key-here",
        
        "_comment": "Timeouts (in milliseconds)",
        "TAVILY_TIMEOUT": "10000",
        "EXA_TIMEOUT": "15000",
        "LINKUP_TIMEOUT": "10000",
        "FIRECRAWL_TIMEOUT": "30000",
        "PERPLEXITY_TIMEOUT": "20000",
        
        "_comment": "Caching",
        "CACHE_TTL": "300",
        "REDIS_CACHE_ENABLED": "false",
        
        "_comment": "Logging and Debug",
        "LOG_LEVEL": "INFO",
        
        "_comment": "Budget Control",
        "DEFAULT_BUDGET": "0.10"
      }
    }
  }
}
```

### Alternative Installation Methods

#### Using UV (Recommended for Development)

```json
{
  "mcpServers": {
    "mcp-search-hub": {
      "command": "uvx",
      "args": [
        "--from", 
        "git+https://github.com/BjornMelin/mcp-search-hub@main",
        "mcp-search-hub"
      ],
      "env": {
        "TAVILY_API_KEY": "tvly-your-api-key-here",
        "EXA_API_KEY": "exa-your-api-key-here"
      }
    }
  }
}
```

#### Using Virtual Environment

```json
{
  "mcpServers": {
    "mcp-search-hub": {
      "command": "/path/to/your/venv/bin/python",
      "args": ["-m", "mcp_search_hub.main", "--transport", "stdio"],
      "env": {
        "TAVILY_API_KEY": "tvly-your-api-key-here",
        "EXA_API_KEY": "exa-your-api-key-here"
      }
    }
  }
}
```

## Troubleshooting

### Common Issues and Solutions

#### ❌ "Module not found: mcp_search_hub"
**Solution**: Ensure MCP Search Hub is installed in the Python environment accessible to Claude Desktop:
```bash
# Install in the correct environment
python -m pip install -r requirements.txt

# Verify installation
python -c "import mcp_search_hub; print('Installation successful')"
```

#### ❌ "Provider XYZ failed to initialize"
**Solution**: Check your API keys and provider settings:
```bash
# Test API keys manually
python -c "
import os
print('TAVILY_API_KEY:', 'Set' if os.getenv('TAVILY_API_KEY') else 'Missing')
print('EXA_API_KEY:', 'Set' if os.getenv('EXA_API_KEY') else 'Missing')
"
```

#### ❌ "Connection timeout" or slow responses
**Solution**: Increase timeout values in the configuration:
```json
"env": {
  "TAVILY_TIMEOUT": "20000",
  "EXA_TIMEOUT": "25000",
  "LINKUP_TIMEOUT": "20000"
}
```

#### ❌ Node.js dependency issues
**Solution**: Install Node.js v16+ for provider MCP servers:
```bash
# Check Node.js version
node --version

# Install Node.js if missing (Ubuntu/Debian)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### Debug Mode

Enable debug logging for troubleshooting:

```json
{
  "mcpServers": {
    "mcp-search-hub": {
      "command": "python",
      "args": ["-m", "mcp_search_hub.main", "--transport", "stdio", "--debug"],
      "env": {
        "LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

Debug logs will be available in the Claude Desktop developer console.

### Testing Configuration

Test your configuration before using it with Claude Desktop:

```bash
# Test STDIO transport
python test_stdio.py

# Test individual providers
python -c "
from mcp_search_hub.server import SearchServer
import asyncio

async def test():
    server = SearchServer()
    await server.initialize()
    info = await server.get_provider_info()
    print('Available providers:', [p['name'] for p in info['providers']])

asyncio.run(test())
"
```

## Usage Examples

### Basic Web Search
```
Search for recent developments in quantum computing using multiple providers
```

### Academic Research
```
Use Exa to find recent research papers about machine learning in healthcare
```

### Competitor Analysis
```
Use Exa to find competitors for Stripe in the payment processing space
```

### Web Scraping
```
Use Firecrawl to scrape the pricing page of example.com and extract structured data
```

### Deep Research
```
Use Firecrawl's deep research to comprehensively analyze the current state of renewable energy adoption
```

### AI-Powered Analysis
```
Use Perplexity to research and reason about the implications of recent AI regulation proposals
```

## Performance and Limits

### Provider Limits
- **Tavily**: 1000 searches/month (free tier)
- **Exa**: 1000 searches/month (free tier)  
- **Linkup**: Usage-based pricing
- **Firecrawl**: 500 pages/month (free tier)
- **Perplexity**: 100 queries/month (free tier)

### Performance Tips
- Use the unified `search` tool for intelligent provider selection
- Enable caching to reduce API calls for repeated queries
- Set appropriate timeout values based on your use case
- Monitor usage with the `get_provider_info` tool

## Support

### Getting Help
- **Documentation**: Check [CLAUDE.md](../CLAUDE.md) for technical details
- **Issues**: Report problems on [GitHub Issues](https://github.com/BjornMelin/mcp-search-hub/issues)
- **Examples**: See [examples/claude-config/](../examples/claude-config/) for additional configurations

### Contributing
- **Development**: See [../developers/contributing.md](../../developers/contributing.md) for development setup
- **Testing**: Run `uv run pytest` to verify functionality
- **Documentation**: Help improve this guide by submitting PRs

---

**Ready to start searching?** Restart Claude Desktop and try asking: *"What search tools do you have available?"*