"""Domain model exports."""

from .health import HealthResponse, HealthStatus, ProviderHealth
from .query import SearchQuery
from .results import (
    CombinedSearchResponse,
    ProviderCatalogEntry,
    ProviderCatalogResponse,
    ProviderExecution,
    ProviderFailure,
    ProviderItem,
    ProviderResponse,
    ResultSource,
    SearchResult,
)

__all__ = [
    "CombinedSearchResponse",
    "HealthResponse",
    "HealthStatus",
    "ProviderCatalogEntry",
    "ProviderCatalogResponse",
    "ProviderExecution",
    "ProviderFailure",
    "ProviderHealth",
    "ProviderItem",
    "ProviderResponse",
    "ResultSource",
    "SearchQuery",
    "SearchResult",
]
