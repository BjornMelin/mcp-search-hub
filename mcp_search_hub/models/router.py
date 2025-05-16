"""Router-specific models for scoring and provider selection."""

from enum import Enum

from pydantic import BaseModel, Field

from .results import SearchResponse


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


class TimeoutConfig(BaseModel):
    """Configuration for dynamic timeout management."""

    base_timeout_ms: int = Field(
        default=10000, description="Base timeout in milliseconds"
    )
    min_timeout_ms: int = Field(
        default=3000, description="Minimum allowed timeout in milliseconds"
    )
    max_timeout_ms: int = Field(
        default=30000, description="Maximum allowed timeout in milliseconds"
    )
    complexity_factor: float = Field(
        default=0.5, description="How much complexity affects timeout (0-1)"
    )


class CascadeExecutionPolicy(BaseModel):
    """Policy configuration for cascade execution behavior."""

    cascade_on_success: bool = Field(
        default=False,
        description="Continue cascade even after successful response",
    )
    min_successful_providers: int = Field(
        default=1,
        description="Minimum number of successful providers needed",
    )
    secondary_delay_ms: int = Field(
        default=0,
        description="Delay before executing secondary providers (milliseconds)",
    )
    circuit_breaker_max_failures: int = Field(
        default=3,
        description="Maximum failures before circuit breaker opens",
    )
    circuit_breaker_reset_timeout: float = Field(
        default=30.0,
        description="Timeout before circuit breaker resets (seconds)",
    )


class ProviderExecutionResult(BaseModel):
    """Result of executing a single provider in cascade."""

    provider_name: str
    success: bool
    response: SearchResponse | None = None
    error: str | None = None
    duration_ms: float
    is_primary: bool = False
    skipped: bool = Field(
        default=False,
        description="Whether provider was skipped due to circuit breaker",
    )
