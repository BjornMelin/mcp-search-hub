"""
Perplexity MCP wrapper provider using generic implementation.
"""

from .generic_mcp import GenericMCPProvider


class PerplexityMCPProvider(GenericMCPProvider):
    """Wrapper for the Perplexity MCP server using generic base."""

    def __init__(self, api_key: str | None = None):
        super().__init__("perplexity", api_key)
