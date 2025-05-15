"""Base class for all search providers."""

from abc import ABC, abstractmethod
from typing import Any, Dict
from ..models.query import SearchQuery
from ..models.results import SearchResponse


class SearchProvider(ABC):
    """Base class for all search providers."""

    name: str

    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search and return results."""
        pass

    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """Return provider capabilities."""
        pass

    @abstractmethod
    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        pass
