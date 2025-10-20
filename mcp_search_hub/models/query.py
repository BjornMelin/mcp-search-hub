"""Query models used by the orchestrator and routing pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    """Classifies the intent of a search query."""

    GENERAL = "general"
    TECHNICAL = "technical"
    RESEARCH = "research"
    NEWS = "news"
    CODE = "code"


class SearchQuery(BaseModel):
    """User request captured from FastMCP tool invocation."""

    query: str = Field(
        min_length=1, description="Natural language query provided by the caller"
    )
    max_results: int = Field(
        default=10, ge=1, le=50, description="Maximum number of results to return"
    )
    include_raw_content: bool = Field(
        default=False,
        description="Whether providers should return raw content bodies when available",
    )
    advanced: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific knobs forwarded to downstream tools",
    )
    tags: set[str] = Field(
        default_factory=set,
        description="Optional tags supplied by the caller to hint at provider selection",
    )

    def fingerprint_payload(self) -> dict[str, Any]:
        """Return a deterministic payload used to compute cache fingerprints."""

        query_text = str(self.query).strip()

        return {
            "query": query_text,
            "max_results": self.max_results,
            "include_raw_content": self.include_raw_content,
            "advanced": self.advanced,
            "tags": sorted(self.tags),
        }


__all__ = ["QueryIntent", "SearchQuery"]
