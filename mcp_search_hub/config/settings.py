"""Streamlined application settings using standardized configuration patterns."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict

from ..models.config import (
    AuthMiddlewareConfig,
    CacheConfig,
    LoggingMiddlewareConfig,
    MiddlewareConfig,
    ProviderConfig,
    ProvidersConfig,
    RateLimitMiddlewareConfig,
    RetryConfig,
    RetryMiddlewareConfig,
)
from ..models.config import (
    Settings as LegacySettings,
)
from ..utils.config_loader import ConfigLoader, StandardizedSettings


class AppSettings(StandardizedSettings):
    """Main application settings with standardized loading patterns."""

    # Server configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    log_level: str = Field(default="INFO", description="Logging level")
    transport: str = Field(default="streamable-http", description="Transport mode")

    # Cache configuration
    cache_ttl: int = Field(default=3600, description="Legacy cache TTL")
    cache_memory_ttl: int = Field(default=300, description="Memory cache TTL")
    cache_redis_ttl: int = Field(default=3600, description="Redis cache TTL")
    redis_url: str = Field(default="redis://localhost:6379", description="Redis URL")
    redis_enabled: bool = Field(default=False, description="Enable Redis cache")
    cache_prefix: str = Field(default="search:", description="Cache key prefix")
    cache_fingerprint_enabled: bool = Field(
        default=True, description="Enable cache fingerprinting"
    )
    cache_clean_interval: int = Field(default=600, description="Cache cleanup interval")

    # Budget configuration
    default_budget: float | None = Field(
        default=None, description="Default query budget"
    )

    # Retry configuration
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_base_delay: float = Field(default=1.0, description="Base retry delay")
    retry_max_delay: float = Field(default=60.0, description="Maximum retry delay")
    retry_exponential_base: float = Field(
        default=2.0, description="Retry exponential base"
    )
    retry_jitter: bool = Field(default=True, description="Enable retry jitter")

    # Provider configurations - using standardized loading
    linkup_api_key: SecretStr = Field(
        default=SecretStr(""), description="Linkup API key"
    )
    linkup_enabled: bool = Field(default=True, description="Enable Linkup provider")
    linkup_timeout: float = Field(default=5.0, description="Linkup timeout")

    exa_api_key: SecretStr = Field(default=SecretStr(""), description="Exa API key")
    exa_enabled: bool = Field(default=True, description="Enable Exa provider")
    exa_timeout: float = Field(default=5.0, description="Exa timeout")

    perplexity_api_key: SecretStr = Field(
        default=SecretStr(""), description="Perplexity API key"
    )
    perplexity_enabled: bool = Field(
        default=True, description="Enable Perplexity provider"
    )
    perplexity_timeout: float = Field(default=5.0, description="Perplexity timeout")

    tavily_api_key: SecretStr = Field(
        default=SecretStr(""), description="Tavily API key"
    )
    tavily_enabled: bool = Field(default=True, description="Enable Tavily provider")
    tavily_timeout: float = Field(default=5.0, description="Tavily timeout")

    firecrawl_api_key: SecretStr = Field(
        default=SecretStr(""), description="Firecrawl API key"
    )
    firecrawl_enabled: bool = Field(
        default=True, description="Enable Firecrawl provider"
    )
    firecrawl_timeout: float = Field(default=5.0, description="Firecrawl timeout")

    # Auth middleware settings
    auth_api_keys: str = Field(default="", description="Comma-separated API keys")
    auth_skip_paths: str = Field(
        default="/health,/metrics,/docs,/redoc,/openapi.json",
        description="Comma-separated auth skip paths",
    )

    # Rate limit middleware settings
    rate_limit: int = Field(default=100, description="Rate limit per window")
    rate_limit_window: int = Field(default=60, description="Rate limit window")
    global_rate_limit: int = Field(default=1000, description="Global rate limit")
    global_rate_limit_window: int = Field(
        default=60, description="Global rate limit window"
    )
    rate_limit_skip_paths: str = Field(
        default="/health,/metrics", description="Comma-separated rate limit skip paths"
    )

    # Logging middleware settings
    logging_include_headers: bool = Field(
        default=True, description="Include headers in logs"
    )
    logging_include_body: bool = Field(
        default=False, description="Include body in logs"
    )
    logging_max_body_size: int = Field(default=1024, description="Max body size to log")
    sensitive_headers: str = Field(
        default="authorization,x-api-key,cookie,set-cookie",
        description="Comma-separated sensitive headers",
    )

    # Retry middleware settings
    retry_skip_paths: str = Field(
        default="/health,/metrics", description="Comma-separated retry skip paths"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_assignment=True,
    )

    def to_legacy_settings(self) -> LegacySettings:
        """Convert to legacy Settings format for backward compatibility."""
        # Parse comma-separated values using ConfigLoader utilities
        api_keys = ConfigLoader.parse_comma_separated_list(self.auth_api_keys)
        auth_skip_paths = ConfigLoader.parse_comma_separated_list(self.auth_skip_paths)
        rate_limit_skip_paths = ConfigLoader.parse_comma_separated_list(
            self.rate_limit_skip_paths
        )
        sensitive_headers = ConfigLoader.parse_comma_separated_list(
            self.sensitive_headers
        )
        retry_skip_paths = ConfigLoader.parse_comma_separated_list(
            self.retry_skip_paths
        )

        return LegacySettings(
            providers=ProvidersConfig(
                linkup=ProviderConfig(
                    name="linkup",
                    api_key=self.linkup_api_key,
                    enabled=self.linkup_enabled,
                    timeout=self.linkup_timeout,
                ),
                exa=ProviderConfig(
                    name="exa",
                    api_key=self.exa_api_key,
                    enabled=self.exa_enabled,
                    timeout=self.exa_timeout,
                ),
                perplexity=ProviderConfig(
                    name="perplexity",
                    api_key=self.perplexity_api_key,
                    enabled=self.perplexity_enabled,
                    timeout=self.perplexity_timeout,
                ),
                tavily=ProviderConfig(
                    name="tavily",
                    api_key=self.tavily_api_key,
                    enabled=self.tavily_enabled,
                    timeout=self.tavily_timeout,
                ),
                firecrawl=ProviderConfig(
                    name="firecrawl",
                    api_key=self.firecrawl_api_key,
                    enabled=self.firecrawl_enabled,
                    timeout=self.firecrawl_timeout,
                ),
            ),
            log_level=self.log_level,
            cache_ttl=self.cache_ttl,
            cache=CacheConfig(
                name="cache",
                memory_ttl=self.cache_memory_ttl,
                redis_ttl=self.cache_redis_ttl,
                redis_url=self.redis_url,
                redis_enabled=self.redis_enabled,
                prefix=self.cache_prefix,
                fingerprint_enabled=self.cache_fingerprint_enabled,
                clean_interval=self.cache_clean_interval,
            ),
            default_budget=self.default_budget,
            port=self.port,
            host=self.host,
            transport=self.transport,
            retry=RetryConfig(
                max_retries=self.max_retries,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                exponential_base=self.retry_exponential_base,
                jitter=self.retry_jitter,
            ),
            middleware=MiddlewareConfig(
                logging=LoggingMiddlewareConfig(
                    enabled=True,  # Default enabled
                    order=5,  # Default order
                    log_level=self.log_level,
                    include_headers=self.logging_include_headers,
                    include_body=self.logging_include_body,
                    sensitive_headers=sensitive_headers,
                    max_body_size=self.logging_max_body_size,
                ),
                auth=AuthMiddlewareConfig(
                    enabled=True,  # Default enabled
                    order=10,  # Default order
                    api_keys=api_keys,
                    skip_auth_paths=auth_skip_paths,
                ),
                rate_limit=RateLimitMiddlewareConfig(
                    enabled=True,  # Default enabled
                    order=20,  # Default order
                    limit=self.rate_limit,
                    window=self.rate_limit_window,
                    global_limit=self.global_rate_limit,
                    global_window=self.global_rate_limit_window,
                    skip_paths=rate_limit_skip_paths,
                ),
                retry=RetryMiddlewareConfig(
                    enabled=True,  # Default enabled
                    order=30,  # Default order
                    max_retries=self.max_retries,
                    base_delay=self.retry_base_delay,
                    max_delay=self.retry_max_delay,
                    exponential_base=self.retry_exponential_base,
                    jitter=self.retry_jitter,
                    skip_paths=retry_skip_paths,
                ),
            ),
        )


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    """Get cached application settings."""
    return AppSettings()


@lru_cache(maxsize=1)
def get_settings() -> LegacySettings:
    """Get settings in legacy format for backward compatibility."""
    app_settings = get_app_settings()
    return app_settings.to_legacy_settings()
