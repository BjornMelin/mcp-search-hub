"""Configuration models.

This module defines the base configuration classes used by various components
in the search hub. These configuration models are built with Pydantic to provide
validation, serialization, and documentation.
"""

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ComponentConfig(BaseModel):
    """Base configuration model for components."""

    name: str = Field(..., description="Component name")
    enabled: bool = Field(True, description="Whether this component is enabled")
    debug: bool = Field(False, description="Enable debug mode for this component")

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")


class ProviderConfig(ComponentConfig):
    """Configuration for a search provider."""

    api_key: SecretStr | None = Field(None, description="API key for the provider")
    enabled: bool = Field(True, description="Whether this provider is enabled")
    timeout_ms: int = Field(30000, description="Timeout in milliseconds")
    max_retries: int = Field(3, description="Maximum number of retries")
    rate_limit_per_minute: int | None = Field(
        None, description="Maximum requests per minute"
    )
    rate_limit_per_hour: int | None = Field(
        None, description="Maximum requests per hour"
    )
    rate_limit_per_day: int | None = Field(None, description="Maximum requests per day")
    concurrent_requests: int = Field(10, description="Maximum concurrent requests")


class RouterConfig(ComponentConfig):
    """Configuration for router components."""

    base_timeout_ms: int = Field(10000, description="Base timeout in milliseconds")
    min_timeout_ms: int = Field(3000, description="Minimum timeout in milliseconds")
    max_timeout_ms: int = Field(30000, description="Maximum timeout in milliseconds")
    max_providers: int = Field(
        3, description="Maximum number of providers to use per query"
    )
    min_confidence: float = Field(
        0.6, description="Minimum confidence threshold for provider selection"
    )
    execution_strategy: str = Field(
        "auto", description="Default execution strategy (auto, parallel, cascade)"
    )
    cascade_on_success: bool = Field(
        False, description="Continue cascade after success"
    )
    min_successful_providers: int = Field(
        1, description="Minimum successful providers needed in cascade"
    )


class ResultProcessorConfig(ComponentConfig):
    """Configuration for result processor components."""

    fuzzy_url_threshold: float = Field(
        92.0, description="Threshold for fuzzy URL matching"
    )
    content_similarity_threshold: float = Field(
        0.85, description="Threshold for content similarity matching"
    )
    use_content_similarity: bool = Field(
        True, description="Whether to use content similarity for deduplication"
    )
    max_results: int = Field(10, description="Maximum number of results to return")


class MergerConfig(ResultProcessorConfig):
    """Configuration for result merger components."""

    provider_weights: dict[str, float] = Field(
        default_factory=dict, description="Per-provider quality weights"
    )
    recency_enabled: bool = Field(True, description="Whether to boost recent results")
    credibility_enabled: bool = Field(
        True, description="Whether to use credibility scoring"
    )
    consensus_weight: float = Field(0.5, description="Weight for consensus boosting")


class PerformanceTrackerConfig(ComponentConfig):
    """Configuration for performance tracking components."""

    history_size: int = Field(100, description="Number of queries to keep in history")
    update_interval_sec: int = Field(
        300, description="Interval between metrics updates in seconds"
    )
    metrics_ttl_sec: int = Field(
        3600, description="Time to live for metrics data in seconds"
    )


class RateLimitConfig(BaseModel):
    """Rate limit configuration for services."""

    requests_per_minute: int | None = Field(
        None, description="Maximum requests per minute"
    )
    requests_per_hour: int | None = Field(None, description="Maximum requests per hour")
    requests_per_day: int | None = Field(None, description="Maximum requests per day")
    concurrent_requests: int = Field(10, description="Maximum concurrent requests")
    cooldown_period: int = Field(5, description="Seconds to wait when rate limited")


class BudgetConfig(BaseModel):
    """Budget configuration for services."""

    default_query_budget: float = Field(0.02, description="Max cost per query")
    daily_budget: float = Field(10.00, description="Max daily cost")
    monthly_budget: float = Field(150.00, description="Max monthly cost")
    enforce_budget: bool = Field(True, description="Whether to enforce budgets")


class CacheConfig(ComponentConfig):
    """Configuration for caching components."""

    memory_ttl: int = Field(300, description="Time to live in seconds for memory cache")
    redis_ttl: int = Field(3600, description="Time to live in seconds for Redis cache")
    redis_url: str = Field("redis://localhost:6379", description="Redis connection URL")
    redis_enabled: bool = Field(
        False, description="Whether to use Redis as cache backend"
    )
    prefix: str = Field("search:", description="Prefix for cache keys")
    fingerprint_enabled: bool = Field(
        True, description="Whether to use semantic fingerprinting"
    )
    clean_interval: int = Field(600, description="Cleanup interval in seconds")


class ProvidersConfig(BaseModel):
    """Configuration for all search providers."""

    linkup: ProviderConfig = ProviderConfig(name="linkup")
    exa: ProviderConfig = ProviderConfig(name="exa")
    perplexity: ProviderConfig = ProviderConfig(name="perplexity")
    tavily: ProviderConfig = ProviderConfig(name="tavily")
    firecrawl: ProviderConfig = ProviderConfig(name="firecrawl")


class RetryConfig(BaseModel):
    """Configuration for exponential backoff retry."""

    max_retries: int = 3
    base_delay: float = 1.0  # Initial delay between retries in seconds
    max_delay: float = 60.0  # Maximum delay between retries in seconds
    exponential_base: float = 2.0  # Base for exponential backoff calculation
    jitter: bool = True  # Whether to add randomization to retry delays


class LoggingMiddlewareConfig(BaseModel):
    """Configuration for logging middleware."""

    enabled: bool = True
    order: int = 5
    log_level: str = "INFO"
    include_headers: bool = True
    include_body: bool = False
    sensitive_headers: list[str] = [
        "authorization",
        "x-api-key",
        "cookie",
        "set-cookie",
    ]
    max_body_size: int = 1024


class AuthMiddlewareConfig(BaseModel):
    """Configuration for authentication middleware."""

    enabled: bool = True
    order: int = 10
    api_keys: list[str] = []
    skip_auth_paths: list[str] = [
        "/health",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    ]


class RateLimitMiddlewareConfig(BaseModel):
    """Configuration for rate limiting middleware."""

    enabled: bool = True
    order: int = 20
    limit: int = 100  # Requests per window
    window: int = 60  # Time window in seconds
    global_limit: int = 1000  # Global requests per window
    global_window: int = 60  # Global time window
    skip_paths: list[str] = ["/health", "/metrics"]


class RetryMiddlewareConfig(BaseModel):
    """Configuration for retry middleware."""

    enabled: bool = True
    order: int = 30
    max_retries: int = 3
    base_delay: float = 1.0  # Initial delay between retries in seconds
    max_delay: float = 60.0  # Maximum delay between retries in seconds
    exponential_base: float = 2.0  # Base for exponential backoff calculation
    jitter: bool = True  # Whether to add randomization to retry delays
    skip_paths: list[str] = ["/health", "/metrics"]


class ErrorHandlerMiddlewareConfig(BaseModel):
    """Configuration for error handler middleware."""

    enabled: bool = True
    order: int = 0  # Should run first to catch all errors
    include_traceback: bool = False
    redact_sensitive_data: bool = True


class MiddlewareConfig(BaseModel):
    """Configuration for middleware components."""

    error_handler: ErrorHandlerMiddlewareConfig = ErrorHandlerMiddlewareConfig()  # Error handler
    logging: LoggingMiddlewareConfig = LoggingMiddlewareConfig()  # Logging middleware
    auth: AuthMiddlewareConfig = AuthMiddlewareConfig()  # Auth middleware
    rate_limit: RateLimitMiddlewareConfig = (
        RateLimitMiddlewareConfig()
    )  # Rate limit middleware
    retry: RetryMiddlewareConfig = RetryMiddlewareConfig()  # Retry middleware


class Settings(BaseModel):
    """Application settings."""

    providers: ProvidersConfig
    log_level: str = "INFO"
    cache_ttl: int = 3600  # Legacy cache TTL in seconds (deprecated)
    cache: CacheConfig = CacheConfig(name="cache")  # New tiered cache configuration
    default_budget: float | None = None
    port: int = 8000
    host: str = "0.0.0.0"
    transport: str = (
        "streamable-http"  # Default to HTTP, can be "stdio" for command-line use
    )
    retry: RetryConfig = RetryConfig()  # Retry configuration with defaults
    middleware: MiddlewareConfig = MiddlewareConfig()  # Middleware components
