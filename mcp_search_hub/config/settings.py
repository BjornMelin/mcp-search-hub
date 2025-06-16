"""Application settings with modern Pydantic v2 patterns."""

from functools import lru_cache

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CacheConfig(BaseModel):
    """Cache configuration settings."""

    redis_url: str = Field(
        default="redis://localhost:6379", description="Redis connection URL"
    )
    memory_ttl: int = Field(
        default=300, ge=0, description="Memory cache TTL in seconds"
    )
    redis_ttl: int = Field(default=3600, ge=0, description="Redis cache TTL in seconds")
    redis_enabled: bool = Field(default=False, description="Enable Redis caching")
    prefix: str = Field(default="search:", description="Cache key prefix")
    fingerprint_enabled: bool = Field(
        default=True, description="Enable semantic fingerprinting"
    )
    clean_interval: int = Field(
        default=600, ge=0, description="Cache cleanup interval in seconds"
    )
    ttl_jitter: int = Field(
        default=60, ge=0, description="Cache TTL jitter in seconds to prevent stampede"
    )


class RetryConfig(BaseModel):
    """Retry configuration settings."""

    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")
    base_delay: float = Field(
        default=1.0, gt=0, description="Base delay between retries"
    )
    max_delay: float = Field(
        default=60.0, gt=0, description="Maximum delay between retries"
    )
    exponential_base: float = Field(
        default=2.0, gt=1, description="Exponential backoff base"
    )
    jitter: bool = Field(default=True, description="Add randomization to retry delays")


class ProviderSettings(BaseModel):
    """Provider configuration settings."""

    api_key: SecretStr = Field(
        default=SecretStr(""), description="API key for the provider"
    )
    enabled: bool = Field(default=True, description="Whether provider is enabled")
    timeout: float = Field(default=30.0, gt=0, description="Request timeout in seconds")


# Router settings
class RouterSettings(BaseModel):
    """Router configuration settings."""

    max_providers: int = Field(
        default=3, ge=1, description="Maximum providers per query"
    )
    min_confidence: float = Field(
        default=0.6, ge=0, le=1, description="Minimum confidence threshold"
    )
    execution_strategy: str = Field(default="auto", description="Execution strategy")
    base_timeout_ms: int = Field(
        default=10000, gt=0, description="Base timeout in milliseconds"
    )
    max_concurrent: int = Field(
        default=3, ge=1, description="Maximum concurrent provider executions"
    )


# Merger settings
class MergerSettings(BaseModel):
    """Merger configuration settings."""

    fuzzy_url_threshold: float = Field(
        default=92.0, description="Threshold for fuzzy URL matching"
    )
    content_similarity_threshold: float = Field(
        default=0.85, description="Threshold for content similarity"
    )
    use_content_similarity: bool = Field(
        default=True, description="Whether to use content similarity"
    )
    max_results: int = Field(
        default=10, description="Maximum number of results to return"
    )
    provider_weights: dict[str, float] = Field(
        default_factory=dict, description="Per-provider quality weights"
    )
    recency_enabled: bool = Field(
        default=True, description="Whether to boost recent results"
    )
    credibility_enabled: bool = Field(
        default=True, description="Whether to use credibility scoring"
    )
    consensus_weight: float = Field(
        default=0.5, description="Weight for consensus boosting"
    )


class MiddlewareConfig(BaseModel):
    """Middleware configuration settings."""

    # Auth middleware
    auth_enabled: bool = Field(default=True, description="Enable authentication")
    auth_api_keys: list[str] = Field(default_factory=list, description="Valid API keys")
    auth_skip_paths: list[str] = Field(
        default_factory=lambda: [
            "/health",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        ],
        description="Paths to skip authentication",
    )

    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests: int = Field(
        default=100, gt=0, description="Requests per window"
    )
    rate_limit_window: int = Field(
        default=60, gt=0, description="Time window in seconds"
    )
    rate_limit_global: int = Field(
        default=1000, gt=0, description="Global requests limit"
    )
    rate_limit_skip_paths: list[str] = Field(
        default_factory=lambda: ["/health", "/metrics"],
        description="Paths to skip rate limiting",
    )

    # Logging
    logging_enabled: bool = Field(default=True, description="Enable request logging")
    logging_include_headers: bool = Field(
        default=True, description="Include headers in logs"
    )
    logging_include_body: bool = Field(
        default=False, description="Include body in logs"
    )
    logging_max_body_size: int = Field(
        default=1024, ge=0, description="Max body size to log"
    )
    logging_sensitive_headers: list[str] = Field(
        default_factory=lambda: ["authorization", "x-api-key", "cookie", "set-cookie"],
        description="Headers to redact from logs",
    )


class AppSettings(BaseSettings):
    """Main application settings with modern Pydantic v2 patterns."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        validate_assignment=True,
        validate_default=True,
    )

    # Application metadata
    app_name: str = Field(default="MCP Search Hub", description="Application name")
    environment: str = Field(default="development", description="Runtime environment")

    # Server configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, ge=1, le=65535, description="Server port")
    log_level: str = Field(default="INFO", description="Logging level")
    transport: str = Field(default="streamable-http", description="Transport mode")

    # Budget
    default_budget: float | None = Field(
        default=None, ge=0, description="Default query budget"
    )

    # LLM routing
    llm_routing_enabled: bool = Field(
        default=False, description="Enable LLM-based routing for complex queries"
    )

    # Provider timeouts (in milliseconds for compatibility)
    linkup_timeout: int = Field(default=10000, gt=0, description="Linkup timeout in ms")
    exa_timeout: int = Field(default=15000, gt=0, description="Exa timeout in ms")
    perplexity_timeout: int = Field(
        default=20000, gt=0, description="Perplexity timeout in ms"
    )
    tavily_timeout: int = Field(default=10000, gt=0, description="Tavily timeout in ms")
    firecrawl_timeout: int = Field(
        default=30000, gt=0, description="Firecrawl timeout in ms"
    )

    # Nested configurations
    cache: CacheConfig = Field(
        default_factory=CacheConfig, description="Cache settings"
    )
    retry: RetryConfig = Field(
        default_factory=RetryConfig, description="Retry settings"
    )
    router: RouterSettings = Field(
        default_factory=RouterSettings, description="Router settings"
    )
    merger: MergerSettings = Field(
        default_factory=MergerSettings, description="Merger settings"
    )
    middleware: MiddlewareConfig = Field(
        default_factory=MiddlewareConfig, description="Middleware settings"
    )

    # Provider configurations
    linkup: ProviderSettings = Field(
        default_factory=ProviderSettings, description="Linkup provider"
    )
    exa: ProviderSettings = Field(
        default_factory=ProviderSettings, description="Exa provider"
    )
    perplexity: ProviderSettings = Field(
        default_factory=ProviderSettings, description="Perplexity provider"
    )
    tavily: ProviderSettings = Field(
        default_factory=ProviderSettings, description="Tavily provider"
    )
    firecrawl: ProviderSettings = Field(
        default_factory=ProviderSettings, description="Firecrawl provider"
    )

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value."""
        valid_envs = {"development", "staging", "production", "test"}
        if v.lower() not in valid_envs:
            raise ValueError(f"Invalid environment: {v}. Must be one of {valid_envs}")
        return v.lower()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()

    def get_provider_config(self, provider_name: str) -> ProviderSettings | None:
        """Get configuration for a specific provider."""
        return getattr(self, provider_name.lower(), None)

    def get_enabled_providers(self) -> list[str]:
        """Get list of enabled provider names."""
        providers = ["linkup", "exa", "perplexity", "tavily", "firecrawl"]
        return [p for p in providers if getattr(self, p).enabled]


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Get cached application settings."""
    return AppSettings()


# Alias for compatibility
get_app_settings = get_settings
