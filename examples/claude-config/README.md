# Claude Configuration Examples

This directory contains example configurations for using MCP Search Hub with various Claude clients.

> **🚀 Quick Setup**: For the fastest setup, use our interactive script: `python scripts/setup_claude_desktop.py`
> 
> **📖 Complete Guide**: See [docs/CLAUDE_DESKTOP_SETUP.md](../../docs/CLAUDE_DESKTOP_SETUP.md) for comprehensive instructions

## Recommended Setup (Single Server)

**MCP Search Hub** embeds all official provider MCP servers internally, providing 35+ tools from 5 providers in one unified interface:

- **Tavily**: Web search and extraction (2 tools)
- **Exa**: Neural search and research (8 tools)  
- **Linkup**: Deep web search (1 tool)
- **Firecrawl**: Web scraping and crawling (8 tools)
- **Perplexity**: AI-powered research (3 tools)
- **Unified**: Intelligent search routing (2 tools)

## Alternative: Multi-Server Setup

The `multi-server-setup.json` file demonstrates how to configure multiple separate MCP servers to work together, but this is generally not recommended as MCP Search Hub already embeds all official servers.

### Setup Instructions

1. Copy the configuration to your Claude Desktop settings:
   ```bash
   # macOS
   ~/Library/Application Support/Claude/config/claude_desktop_config.json
   
   # Windows
   %APPDATA%\Claude\config\claude_desktop_config.json
   
   # Linux
   ~/.config/Claude/config/claude_desktop_config.json
   ```

2. Replace the API keys with your actual keys:
   - `your_firecrawl_api_key`
   - `your_perplexity_api_key` (if using)
   - `your_exa_api_key` (if using)

3. Install the required MCP servers:
   ```bash
   # Firecrawl MCP (official)
   npm install -g firecrawl-mcp
   
   # Perplexity and Exa MCP (if available)
   # Check their respective documentation for installation instructions
   ```

4. Start MCP Search Hub:
   ```bash
   docker-compose up -d
   # or
   python -m mcp_search_hub.main
   ```

5. Restart Claude Desktop

### Usage

Once configured, you'll have access to:

- **Search Hub Tools**:
  - `search()`: Multi-provider search with automatic provider selection
  - `get_provider_info()`: Information about available search providers

- **Firecrawl Tools** (via official MCP server):
  - `firecrawl_scrape_url()`: Advanced web scraping
  - `firecrawl_map_site()`: Discover URLs from a site
  - `firecrawl_crawl_site()`: Crawl entire websites
  - `firecrawl_search()`: Web search with content extraction
  - And more...

### Example Queries

```
# Multi-provider search
search("latest developments in quantum computing", advanced=True)

# Web scraping with Firecrawl
firecrawl_scrape_url("https://example.com", format="markdown")

# Combining tools for research
1. search("AI research papers", providers=["exa", "perplexity"])
2. firecrawl_scrape_url(result.url, format="markdown")
```

### Troubleshooting

- **API Key Issues**: Ensure all API keys are correctly set in the configuration
- **Server Connection**: Verify MCP Search Hub is running on the correct port
- **MCP Server Installation**: Make sure all required MCP servers are installed globally with npm
- **Restart Required**: Always restart Claude Desktop after configuration changes