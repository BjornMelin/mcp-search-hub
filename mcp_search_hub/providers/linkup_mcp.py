"""
Linkup MCP wrapper provider using generic implementation.
"""

from .generic_mcp import GenericMCPProvider
from .retry_mixin import RetryMixin


class LinkupMCPProvider(GenericMCPProvider, RetryMixin):
    """Wrapper for the Linkup MCP server using generic base."""

    def __init__(self, api_key: str | None = None):
        super().__init__("linkup", api_key)

    # Linkup needs custom retry logic
    async def search(self, query):
        """Execute a search query with retry logic."""
        return await self.with_retry(super().search)(query)
