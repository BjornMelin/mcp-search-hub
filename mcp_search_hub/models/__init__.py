"""Domain models for the MCP Search Hub."""

from .health import HealthResponse, HealthStatus, ProviderHealth
from .query import QueryIntent, SearchQuery
from .results import CombinedSearchResponse, ProviderResult, SearchResult

__all__ = [
    "CombinedSearchResponse",
    "HealthResponse",
    "HealthStatus",
    "ProviderHealth",
    "ProviderResult",
    "QueryIntent",
    "SearchQuery",
    "SearchResult",
]
