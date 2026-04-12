"""You.com MCP wrapper provider using generic implementation."""

from .generic_mcp import GenericMCPProvider


class YouMCPProvider(GenericMCPProvider):
    """Wrapper for the You.com MCP server using generic base."""

    def __init__(self, api_key: str | None = None):
        super().__init__("you", api_key)
