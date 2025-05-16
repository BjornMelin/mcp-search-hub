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


class Settings(BaseModel):
    """Application settings."""

    providers: ProvidersConfig
    log_level: str = "INFO"
    cache_ttl: int = 3600  # Cache TTL in seconds
    default_budget: float | None = None
    port: int = 8000
    host: str = "0.0.0.0"
    transport: str = (
        "streamable-http"  # Default to HTTP, can be "stdio" for command-line use
    )
    retry: RetryConfig = RetryConfig()  # Retry configuration with defaults
