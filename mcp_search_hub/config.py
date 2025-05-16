"""Configuration management."""

import os
from functools import lru_cache

from pydantic import SecretStr

from .models.config import ProviderConfig, ProvidersConfig, Settings


@lru_cache
def get_settings() -> Settings:
    """Get application settings, with environment variable overrides."""
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
    )
