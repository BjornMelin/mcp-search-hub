"""Base class for all search providers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple

from ..models.base import HealthStatus
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

    async def check_status(self) -> Tuple[HealthStatus, str]:
        """
        Check the status of the provider.

        Returns:
            A tuple of (status, message) where status is one of
            HealthStatus.OK, HealthStatus.DEGRADED, or HealthStatus.FAILED
        """
        try:
            # Default implementation: try to make a minimal API call
            # to check if the service is responsive
            # Providers can override this with more specific checks

            # Make a minimal query to check if the provider is responsive
            test_query = SearchQuery(query="test", max_results=1)
            response = await self.search(test_query)

            if response.error:
                return (
                    HealthStatus.DEGRADED,
                    f"Provider returning errors: {response.error}",
                )
            return HealthStatus.OK, "Provider is operational"

        except Exception as e:
            return HealthStatus.FAILED, f"Provider check failed: {str(e)}"
