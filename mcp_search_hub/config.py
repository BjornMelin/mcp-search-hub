"""Configuration management."""

import os
from functools import lru_cache

from pydantic import SecretStr

from .models.config import (
    AuthMiddlewareConfig,
    LoggingMiddlewareConfig,
    MiddlewareConfig,
    ProviderConfig,
    ProvidersConfig,
    RateLimitMiddlewareConfig,
    RetryConfig,
    Settings,
)


@lru_cache
def get_settings() -> Settings:
    """Get application settings, with environment variable overrides."""
    # Parse comma-separated API keys from environment
    api_keys_str = os.getenv("MCP_SEARCH_HUB_API_KEY", "")
    api_keys = (
        [k.strip() for k in api_keys_str.split(",") if k.strip()]
        if api_keys_str
        else []
    )

    # Parse comma-separated skip paths from environment
    auth_skip_paths_str = os.getenv(
        "AUTH_SKIP_PATHS", "/health,/metrics,/docs,/redoc,/openapi.json"
    )
    auth_skip_paths = (
        [p.strip() for p in auth_skip_paths_str.split(",") if p.strip()]
        if auth_skip_paths_str
        else []
    )

    rate_limit_skip_paths_str = os.getenv("RATE_LIMIT_SKIP_PATHS", "/health,/metrics")
    rate_limit_skip_paths = (
        [p.strip() for p in rate_limit_skip_paths_str.split(",") if p.strip()]
        if rate_limit_skip_paths_str
        else []
    )

    # Parse comma-separated sensitive headers from environment
    sensitive_headers_str = os.getenv(
        "SENSITIVE_HEADERS", "authorization,x-api-key,cookie,set-cookie"
    )
    sensitive_headers = (
        [h.strip() for h in sensitive_headers_str.split(",") if h.strip()]
        if sensitive_headers_str
        else []
    )
    
    # Parse comma-separated retry skip paths from environment
    retry_skip_paths_str = os.getenv("RETRY_SKIP_PATHS", "/health,/metrics")
    retry_skip_paths = (
        [p.strip() for p in retry_skip_paths_str.split(",") if p.strip()]
        if retry_skip_paths_str
        else []
    )

    return Settings(
        providers=ProvidersConfig(
            linkup=ProviderConfig(
                api_key=SecretStr(os.getenv("LINKUP_API_KEY", "")),
                enabled=os.getenv("LINKUP_ENABLED", "true").lower() == "true",
                timeout=float(os.getenv("LINKUP_TIMEOUT", "5.0")),
            ),
            exa=ProviderConfig(
                api_key=SecretStr(os.getenv("EXA_API_KEY", "")),
                enabled=os.getenv("EXA_ENABLED", "true").lower() == "true",
                timeout=float(os.getenv("EXA_TIMEOUT", "5.0")),
            ),
            perplexity=ProviderConfig(
                api_key=SecretStr(os.getenv("PERPLEXITY_API_KEY", "")),
                enabled=os.getenv("PERPLEXITY_ENABLED", "true").lower() == "true",
                timeout=float(os.getenv("PERPLEXITY_TIMEOUT", "5.0")),
            ),
            tavily=ProviderConfig(
                api_key=SecretStr(os.getenv("TAVILY_API_KEY", "")),
                enabled=os.getenv("TAVILY_ENABLED", "true").lower() == "true",
                timeout=float(os.getenv("TAVILY_TIMEOUT", "5.0")),
            ),
            firecrawl=ProviderConfig(
                api_key=SecretStr(os.getenv("FIRECRAWL_API_KEY", "")),
                enabled=os.getenv("FIRECRAWL_ENABLED", "true").lower() == "true",
                timeout=float(os.getenv("FIRECRAWL_TIMEOUT", "5.0")),
            ),
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        cache_ttl=int(os.getenv("CACHE_TTL", "3600")),
        default_budget=(
            float(os.getenv("DEFAULT_BUDGET")) if os.getenv("DEFAULT_BUDGET") else None
        ),
        port=int(os.getenv("PORT", "8000")),
        host=os.getenv("HOST", "0.0.0.0"),
        transport=os.getenv("TRANSPORT", "streamable-http"),
        retry=RetryConfig(
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            base_delay=float(os.getenv("RETRY_BASE_DELAY", "1.0")),
            max_delay=float(os.getenv("RETRY_MAX_DELAY", "60.0")),
            exponential_base=float(os.getenv("RETRY_EXPONENTIAL_BASE", "2.0")),
            jitter=os.getenv("RETRY_JITTER", "true").lower() == "true",
        ),
        middleware=MiddlewareConfig(
            logging=LoggingMiddlewareConfig(
                enabled=os.getenv("LOGGING_MIDDLEWARE_ENABLED", "true").lower()
                == "true",
                order=int(os.getenv("LOGGING_MIDDLEWARE_ORDER", "5")),
                log_level=os.getenv("LOGGING_MIDDLEWARE_LOG_LEVEL", "INFO"),
                include_headers=os.getenv("LOGGING_INCLUDE_HEADERS", "true").lower()
                == "true",
                include_body=os.getenv("LOGGING_INCLUDE_BODY", "false").lower()
                == "true",
                sensitive_headers=sensitive_headers,
                max_body_size=int(os.getenv("LOGGING_MAX_BODY_SIZE", "1024")),
            ),
            auth=AuthMiddlewareConfig(
                enabled=os.getenv("AUTH_MIDDLEWARE_ENABLED", "true").lower() == "true",
                order=int(os.getenv("AUTH_MIDDLEWARE_ORDER", "10")),
                api_keys=api_keys,
                skip_auth_paths=auth_skip_paths,
            ),
            rate_limit=RateLimitMiddlewareConfig(
                enabled=os.getenv("RATE_LIMIT_MIDDLEWARE_ENABLED", "true").lower()
                == "true",
                order=int(os.getenv("RATE_LIMIT_MIDDLEWARE_ORDER", "20")),
                limit=int(os.getenv("RATE_LIMIT", "100")),
                window=int(os.getenv("RATE_LIMIT_WINDOW", "60")),
                global_limit=int(os.getenv("GLOBAL_RATE_LIMIT", "1000")),
                global_window=int(os.getenv("GLOBAL_RATE_LIMIT_WINDOW", "60")),
                skip_paths=rate_limit_skip_paths,
            ),
            retry=RetryMiddlewareConfig(
                enabled=os.getenv("RETRY_MIDDLEWARE_ENABLED", "true").lower() == "true",
                order=int(os.getenv("RETRY_MIDDLEWARE_ORDER", "30")),
                max_retries=int(os.getenv("MAX_RETRIES", "3")),
                base_delay=float(os.getenv("RETRY_BASE_DELAY", "1.0")),
                max_delay=float(os.getenv("RETRY_MAX_DELAY", "60.0")),
                exponential_base=float(os.getenv("RETRY_EXPONENTIAL_BASE", "2.0")),
                jitter=os.getenv("RETRY_JITTER", "true").lower() == "true",
                skip_paths=retry_skip_paths,
            ),
        ),
    )
