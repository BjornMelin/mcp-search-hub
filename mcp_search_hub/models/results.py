"""Typed provider and federated search results."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field, WithJsonSchema

ExactUSD = Annotated[
    Decimal,
    Field(ge=Decimal("0")),
    WithJsonSchema({"type": "string"}, mode="serialization"),
]


class ProviderItem(BaseModel):
    """Normalized result returned by one provider before fusion."""

    title: str = ""
    url: str | None = None
    snippet: str | None = None
    raw_content: str | None = None
    original_score: float | None = Field(default=None, allow_inf_nan=False)
    metadata: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    provider_rank: int | None = Field(default=None, ge=1, exclude=True)


class ProviderResponse(BaseModel):
    """Successful provider execution."""

    provider: str
    latency_ms: float = Field(ge=0.0, allow_inf_nan=False)
    results: list[ProviderItem] = Field(default_factory=lambda: list[ProviderItem]())


class ResultSource(BaseModel):
    """Provenance for one provider contribution to a fused result."""

    provider: str
    rank: int = Field(ge=1)
    original_score: float | None = Field(default=None, allow_inf_nan=False)


class SearchResult(BaseModel):
    """One deduplicated result ranked with reciprocal-rank fusion."""

    title: str = ""
    url: str | None = None
    snippet: str | None = None
    raw_content: str | None = None
    score: float = Field(ge=0.0, allow_inf_nan=False)
    sources: list[ResultSource] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())


class ProviderExecution(BaseModel):
    """Compact execution evidence for one successful provider."""

    provider: str
    latency_ms: float = Field(ge=0.0, allow_inf_nan=False)
    result_count: int = Field(ge=0)


class ProviderFailure(BaseModel):
    """Sanitized provider failure."""

    provider: str
    error_type: str


class ProviderCatalogEntry(BaseModel):
    """Public routing and cost metadata for one configured provider."""

    identifier: str
    tool: str
    tags: list[str]
    weight: float = Field(gt=0.0, allow_inf_nan=False)
    timeout_seconds: float = Field(gt=0.0, allow_inf_nan=False)
    estimated_cost_usd: ExactUSD


class ProviderCatalogResponse(BaseModel):
    """Typed response from the provider catalog tool."""

    providers: list[ProviderCatalogEntry]


class CombinedSearchResponse(BaseModel):
    """Public deterministic response from the search tool."""

    query: str
    results: list[SearchResult] = Field(default_factory=lambda: list[SearchResult]())
    selected_providers: list[str] = Field(default_factory=lambda: list[str]())
    successful_providers: list[ProviderExecution] = Field(
        default_factory=lambda: list[ProviderExecution]()
    )
    failed_providers: list[ProviderFailure] = Field(default_factory=lambda: list[ProviderFailure]())
    timed_out_providers: list[str] = Field(default_factory=lambda: list[str]())
    inferred_tags: list[str] = Field(default_factory=lambda: list[str]())
    estimated_cost_usd: ExactUSD
    elapsed_ms: float = Field(ge=0.0, allow_inf_nan=False)


__all__ = [
    "CombinedSearchResponse",
    "ProviderCatalogEntry",
    "ProviderCatalogResponse",
    "ProviderExecution",
    "ProviderFailure",
    "ProviderItem",
    "ProviderResponse",
    "ResultSource",
    "SearchResult",
]
