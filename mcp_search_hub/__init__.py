"""MCP Search Hub package metadata."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mcp-search-hub")
except PackageNotFoundError:  # source checkout before installation
    __version__ = "0+unknown"

__all__ = ["__version__"]
