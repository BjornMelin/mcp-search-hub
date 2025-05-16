"""Error handling utilities."""

import traceback
from typing import Any


class SearchError(Exception):
    """Base class for search-related exceptions."""

    def __init__(self, message: str, provider: str | None = None):
        self.message = message
        self.provider = provider
        super().__init__(message)


class ProviderError(SearchError):
    """Exception raised when a provider fails."""


class QueryError(SearchError):
    """Exception raised when there's an issue with the query."""


class RouterError(SearchError):
    """Exception raised when routing fails."""


def format_exception(e: Exception) -> dict[str, Any]:
    """Format an exception for structured logging."""
    return {
        "error_type": e.__class__.__name__,
        "message": str(e),
        "traceback": traceback.format_exc(),
    }
