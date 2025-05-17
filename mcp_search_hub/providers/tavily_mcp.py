"""
Tavily MCP wrapper provider using generic implementation.
"""

from .generic_mcp import GenericMCPProvider


class TavilyMCPProvider(GenericMCPProvider):
    """Wrapper for the Tavily MCP server using generic base."""

    def __init__(self, api_key: str | None = None):
        super().__init__("tavily", api_key)
