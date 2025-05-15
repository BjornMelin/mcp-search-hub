"""Result models."""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional


class SearchResult(BaseModel):
    """A single search result."""

    title: str = Field(..., description="Result title")
    url: str = Field(..., description="Result URL")
    snippet: str = Field(..., description="Result snippet or summary")
    source: str = Field(..., description="Source provider")
    score: float = Field(..., description="Relevance score")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class SearchResponse(BaseModel):
    """Response from a search provider."""

    results: List[SearchResult] = Field(..., description="Search results")
    query: str = Field(..., description="Original query")
    total_results: int = Field(..., description="Total number of results")
    provider: str = Field(..., description="Provider name")
    timing_ms: Optional[float] = Field(None, description="Search time in milliseconds")
    error: Optional[str] = Field(
        None, description="Error message if something went wrong"
    )


class CombinedSearchResponse(BaseModel):
    """Combined response from multiple search providers."""

    results: List[SearchResult] = Field(..., description="Combined search results")
    query: str = Field(..., description="Original query")
    providers_used: List[str] = Field(..., description="Providers used for the search")
    total_results: int = Field(..., description="Total number of results")
    total_cost: float = Field(..., description="Total cost of the search")
    timing_ms: float = Field(..., description="Total search time in milliseconds")
