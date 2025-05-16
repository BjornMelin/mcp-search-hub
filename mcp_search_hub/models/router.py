"""Router-specific models for scoring and provider selection."""

from enum import Enum

from pydantic import BaseModel, Field


class ScoringMode(str, Enum):
    """Scoring modes for combining multiple scores."""

    MULTIPLY = "multiply"
    MAX = "max"
    AVG = "avg"
    SUM = "sum"


class ProviderScore(BaseModel):
    """Score data for a specific provider."""

    provider_name: str
    base_score: float = Field(ge=0.0, description="Base score from feature matching")
    performance_score: float = Field(
        ge=0.0, default=1.0, description="Historical performance score"
    )
    recency_bonus: float = Field(ge=0.0, default=0.0, description="Bonus for recency")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence level in score (0-1)"
    )
    weighted_score: float = Field(ge=0.0, description="Final weighted score")
    explanation: str | None = Field(
        default=None, description="Human-readable explanation of score"
    )


class RoutingDecision(BaseModel):
    """Results of the routing decision process."""

    query_id: str
    selected_providers: list[str]
    provider_scores: list[ProviderScore]
    score_mode: ScoringMode
    confidence: float = Field(
        ge=0.0, le=1.0, description="Overall confidence in routing decision"
    )
    explanation: str = Field(description="Explanation of routing decision")
    metadata: dict = Field(default_factory=dict)


class ProviderPerformanceMetrics(BaseModel):
    """Performance metrics for a provider."""

    provider_name: str
    avg_response_time: float = Field(
        ge=0.0, description="Average response time in milliseconds"
    )
    success_rate: float = Field(
        ge=0.0, le=1.0, description="Success rate as a percentage"
    )
    avg_result_quality: float = Field(
        ge=0.0, le=1.0, description="Average result quality score"
    )
    total_queries: int = Field(ge=0, description="Total number of queries processed")
    last_updated: str | None = Field(
        default=None, description="ISO datetime of last update"
    )
