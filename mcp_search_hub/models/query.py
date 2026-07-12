"""Typed public search request."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchQuery(BaseModel):
    """One federated search request."""

    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=4000)
    max_results: int = Field(default=10, ge=1, le=100)
    include_raw_content: bool = False
    providers: list[str] | None = None
    tags: set[str] = Field(default_factory=set)
    timeout_seconds: float = Field(default=20.0, gt=0.0, le=300.0)
    budget_usd: Decimal | None = Field(default=None, gt=Decimal("0"))

    @field_validator("providers")
    @classmethod
    def normalize_providers(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = list(dict.fromkeys(item.strip().lower() for item in value))
        if not normalized or any(not item for item in normalized):
            raise ValueError("providers must contain non-empty identifiers")
        return normalized

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: set[str]) -> set[str]:
        return {tag.strip().lower() for tag in value if tag.strip()}


__all__ = ["SearchQuery"]
