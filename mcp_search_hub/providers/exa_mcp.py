"""
Exa MCP wrapper provider using generic implementation.
"""

from .generic_mcp import GenericMCPProvider


class ExaMCPProvider(GenericMCPProvider):
    """Wrapper for the Exa MCP server using generic base."""

    def __init__(self, api_key: str | None = None):
        super().__init__("exa", api_key)
