"""Configuration models."""


from pydantic import BaseModel, SecretStr


class ProviderConfig(BaseModel):
    """Configuration for a search provider."""

    api_key: SecretStr
    enabled: bool = True
    timeout: float = 5.0  # Timeout in seconds


class ProvidersConfig(BaseModel):
    """Configuration for all search providers."""

    linkup: ProviderConfig
    exa: ProviderConfig
    perplexity: ProviderConfig
    tavily: ProviderConfig
    firecrawl: ProviderConfig


class RetryConfig(BaseModel):
    """Configuration for exponential backoff retry."""

    max_retries: int = 3
    base_delay: float = 1.0  # Initial delay between retries in seconds
    max_delay: float = 60.0  # Maximum delay between retries in seconds
    exponential_base: float = 2.0  # Base for exponential backoff calculation
    jitter: bool = True  # Whether to add randomization to retry delays


class CacheConfig(BaseModel):
    """Configuration for caching system."""

    memory_ttl: int = 300  # 5 minutes for memory cache
    redis_ttl: int = 3600  # 1 hour for Redis cache
    redis_url: str = "redis://localhost:6379"
    redis_enabled: bool = False  # Default to disabled until explicitly enabled
    prefix: str = "search:"
    fingerprint_enabled: bool = True  # Enable semantic query fingerprinting
    clean_interval: int = 600  # Cleanup interval in seconds


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


class MiddlewareConfig(BaseModel):
    """Configuration for middleware components."""

    logging: LoggingMiddlewareConfig = LoggingMiddlewareConfig()
    auth: AuthMiddlewareConfig = AuthMiddlewareConfig()
    rate_limit: RateLimitMiddlewareConfig = RateLimitMiddlewareConfig()
    retry: RetryMiddlewareConfig = RetryMiddlewareConfig()


class Settings(BaseModel):
    """Application settings."""

    providers: ProvidersConfig
    log_level: str = "INFO"
    cache_ttl: int = 3600  # Legacy cache TTL in seconds (deprecated)
    cache: CacheConfig = CacheConfig()  # New tiered cache configuration
    default_budget: float | None = None
    port: int = 8000
    host: str = "0.0.0.0"
    transport: str = (
        "streamable-http"  # Default to HTTP, can be "stdio" for command-line use
    )
    retry: RetryConfig = RetryConfig()  # Retry configuration with defaults
    middleware: MiddlewareConfig = MiddlewareConfig()  # Middleware configuration
