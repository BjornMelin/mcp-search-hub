"""Configuration for provider implementations."""

from .base_mcp import ServerType

# Provider configurations for all MCP providers
PROVIDER_CONFIGS = {
    "exa": {
        "env_var": "EXA_API_KEY",
        "server_type": ServerType.NODE_JS,
        "package": "exa-mcp-server",
        "tool_name": "web_search_exa",
        "timeout": 15000,
    },
    "firecrawl": {
        "env_var": "FIRECRAWL_API_KEY",
        "server_type": ServerType.NODE_JS,
        "package": "firecrawl-mcp",
        "tool_name": "firecrawl_search",
        "timeout": 30000,
        # Command-line args
        "args": ["firecrawl-mcp"],
    },
    "linkup": {
        "env_var": "LINKUP_API_KEY",
        "server_type": ServerType.PYTHON,
        "package": "mcp-search-linkup",
        "tool_name": "linkup_search_web",
        "timeout": 10000,
        # Python module execution
        "args": ["-m", "mcp_search_linkup"],
    },
    "perplexity": {
        "env_var": "PERPLEXITY_API_KEY",
        "server_type": ServerType.NODE_JS,
        "package": "@ppl-ai/perplexity-mcp",
        "tool_name": "perplexity_ask",
        "timeout": 20000,
        "args": ["perplexity-mcp"],
    },
    "tavily": {
        "env_var": "TAVILY_API_KEY",
        "server_type": ServerType.NODE_JS,
        "package": "tavily-mcp@0.2.0",
        "tool_name": "tavily_search",
        "timeout": 10000,
        "args": ["tavily-mcp@0.2.0"],
    },
}
