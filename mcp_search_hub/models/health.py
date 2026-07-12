"""Health reporting models for the MCP Search Hub."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
    """Enumeration of supported health states."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ProviderHealth(BaseModel):
    """Status payload describing the health of a provider session."""

    identifier: str = Field(description="Provider identifier")
    status: HealthStatus = Field(description="Current provider status")
    message: str | None = Field(default=None, description="Optional human friendly message")
    latency_ms: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
        description="Latency of the most recent completed attempt in milliseconds",
    )
    consecutive_failures: int = Field(
        default=0, ge=0, description="Number of consecutive failed attempts"
    )


class HealthResponse(BaseModel):
    """Aggregate health response exposed via the HTTP `/health` endpoint."""

    status: HealthStatus = Field(description="Overall hub status")
    healthy_providers: int = Field(ge=0, description="Count of healthy providers")
    total_providers: int = Field(ge=0, description="Total providers tracked by the hub")
    providers: dict[str, ProviderHealth] = Field(
        default_factory=dict,
        description="Mapping of provider identifier to health data",
    )
    extra: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


__all__ = ["HealthResponse", "HealthStatus", "ProviderHealth"]
