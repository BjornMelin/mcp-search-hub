"""
Firecrawl MCP wrapper provider using generic implementation.
"""

from .generic_mcp import GenericMCPProvider


class FirecrawlMCPProvider(GenericMCPProvider):
    """Wrapper for the Firecrawl MCP server using generic base."""

    def __init__(self, api_key: str | None = None):
        super().__init__("firecrawl", api_key)
