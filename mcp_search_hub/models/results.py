"""Result models."""

from typing import Any

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """A single search result."""

    title: str = Field(..., description="Result title")
    url: str = Field(..., description="Result URL")
    snippet: str = Field(..., description="Result snippet or summary")
    source: str = Field(..., description="Source provider")
    score: float = Field(..., description="Relevance score")
    raw_content: str | None = Field(
        None, description="Raw content of the result when requested"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class SearchResponse(BaseModel):
    """Response from a search provider."""

    results: list[SearchResult] = Field(..., description="Search results")
    query: str = Field(..., description="Original query")
    total_results: int = Field(..., description="Total number of results")
    provider: str = Field(..., description="Provider name")
    timing_ms: float | None = Field(None, description="Search time in milliseconds")
    error: str | None = Field(None, description="Error message if something went wrong")
    cost: float | None = Field(None, description="Cost of the search in USD")
    rate_limited: bool = Field(
        False, description="Whether the provider was rate limited"
    )
    budget_exceeded: bool = Field(
        False, description="Whether the provider budget was exceeded"
    )


class CombinedSearchResponse(BaseModel):
    """Combined response from multiple search providers."""

    results: list[SearchResult] = Field(..., description="Combined search results")
    query: str = Field(..., description="Original query")
    providers_used: list[str] = Field(..., description="Providers used for the search")
    total_results: int = Field(..., description="Total number of results")
    total_cost: float = Field(0.0, description="Total cost of the search")
    timing_ms: float = Field(..., description="Total search time in milliseconds")
    provider_costs: dict[str, float] = Field(
        default_factory=dict, description="Cost breakdown by provider"
    )
    rate_limited_providers: list[str] = Field(
        default_factory=list, description="Providers that were rate limited"
    )
    budget_exceeded_providers: list[str] = Field(
        default_factory=list, description="Providers that exceeded their budget"
    )
