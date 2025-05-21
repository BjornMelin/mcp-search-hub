"""
Linkup MCP wrapper provider using generic implementation.
"""

from .generic_mcp import GenericMCPProvider


class LinkupMCPProvider(GenericMCPProvider):
    """Wrapper for the Linkup MCP server using generic base."""

    def __init__(self, api_key: str | None = None):
        super().__init__("linkup", api_key)
        
    # No need for custom search method anymore, as retry logic is now in BaseMCPProvider
