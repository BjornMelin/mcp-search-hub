"""Application configuration leveraging Pydantic v2 settings."""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from functools import lru_cache
from typing import Any, TypeAlias, cast

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..providers.sessions import ProviderDefinition

TransportConfig: TypeAlias = dict[str, Any] | str


class CacheConfig(BaseModel):
    """Cache configuration."""

    redis_url: str | None = Field(default=None, description="Redis connection URL")
    redis_enabled: bool = Field(default=False, description="Enable Redis caching")
    memory_ttl: int = Field(default=300, ge=0, description="In-memory TTL in seconds")
    redis_ttl: int = Field(default=1800, ge=0, description="Redis TTL in seconds")
    prefix: str = Field(default="search", description="Cache key prefix")
    ttl_jitter: int = Field(
        default=30, ge=0, description="Jitter in seconds to avoid stampedes"
    )


class RetryConfig(BaseModel):
    """Retry middleware configuration."""

    max_retries: int = Field(default=2, ge=0)
    base_delay: float = Field(default=1.0, ge=0.0)
    max_delay: float = Field(default=30.0, ge=0.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)


class RouterSettings(BaseModel):
    """Routing planner configuration."""

    max_providers: int = Field(default=3, ge=1, le=5)


class ResultConfig(BaseModel):
    """Result aggregation configuration."""

    max_results: int = Field(default=10, ge=1, le=50)


class MiddlewareConfig(BaseModel):
    """Middleware toggles for HTTP transport."""

    auth_enabled: bool = Field(default=False)
    auth_api_keys: list[str] = Field(default_factory=list)
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_requests: int = Field(default=60, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    structured_logging: bool = Field(default=True)
    include_payloads: bool = Field(default=False)


class ProviderSettings(BaseModel):
    """Declarative provider configuration."""

    enabled: bool = Field(default=True)
    transport: str | dict[str, Any] | None = Field(
        default=None, description="Transport configuration or command string"
    )
    command: list[str] | None = Field(
        default=None, description="Command array if transport absent"
    )
    api_key: SecretStr | None = Field(default=None, description="Optional API key")
    default_tool: str = Field(default="search")
    title: str | None = Field(default=None)
    timeout: float = Field(default=30.0, gt=0)
    tags: list[str] = Field(default_factory=list)
    weight: float = Field(default=1.0, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    failure_threshold: int = Field(default=3, ge=1)

    def build_definition(self, identifier: str) -> ProviderDefinition | None:
        """Construct a provider definition when the provider is enabled."""

        if not self.enabled:
            return None

        transport_config = self._resolve_transport()
        if transport_config is None:
            return None

        environment: dict[str, str] = dict(self.env)
        secret_obj = cast(SecretStr | None, getattr(self, "api_key", None))
        if isinstance(secret_obj, SecretStr):
            secret_value = secret_obj.get_secret_value().strip()
            if secret_value:
                environment.setdefault("API_KEY", secret_value)

        transport = self._apply_env_to_transport(transport_config, environment)

        return ProviderDefinition(
            identifier=identifier,
            transport=transport,
            tool=self.default_tool,
            title=self.title or identifier.title(),
            tags=set(self.tags),
            weight=self.weight,
            timeout=self.timeout,
            metadata=self.metadata,
            failure_threshold=self.failure_threshold,
        )

    def _resolve_transport(self) -> TransportConfig | None:
        """Return the configured transport string or mapping if present."""

        transport_value = cast(TransportConfig | None, getattr(self, "transport", None))
        if isinstance(transport_value, dict):
            return dict(transport_value)
        if isinstance(transport_value, str):
            stripped = transport_value.strip()
            if stripped:
                return stripped
        command_value = cast(list[str] | None, getattr(self, "command", None))
        if command_value:
            return {"command": list(command_value)}
        return None

    def _apply_env_to_transport(
        self, transport_config: TransportConfig, env: Mapping[str, str]
    ) -> TransportConfig | dict[str, Any]:
        """Merge environment variables into the resolved transport when required."""

        if isinstance(transport_config, dict):
            concrete = dict(transport_config)
            if env:
                merged_env = dict(concrete.get("env", {}))
                merged_env.update(env)
                concrete["env"] = merged_env
            return concrete

        if env:
            return {"command": shlex.split(transport_config), "env": dict(env)}

        return transport_config


class AppSettings(BaseSettings):
    """Primary application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="MCP Search Hub")
    environment: str = Field(default="development")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = Field(default="INFO")
    transport: str = Field(default="streamable-http")
    streamable_http_path: str = Field(default="/mcp")

    cache: CacheConfig = Field(default_factory=CacheConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    router: RouterSettings = Field(default_factory=RouterSettings)
    results: ResultConfig = Field(default_factory=ResultConfig)
    middleware: MiddlewareConfig = Field(default_factory=MiddlewareConfig)

    linkup: ProviderSettings = Field(default_factory=ProviderSettings)
    exa: ProviderSettings = Field(default_factory=ProviderSettings)
    perplexity: ProviderSettings = Field(default_factory=ProviderSettings)
    tavily: ProviderSettings = Field(default_factory=ProviderSettings)
    firecrawl: ProviderSettings = Field(default_factory=ProviderSettings)

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        """Normalise environment identifiers from configuration sources."""

        allowed = {"development", "staging", "production", "test"}
        if value.lower() not in allowed:
            raise ValueError(f"Invalid environment '{value}'. Must be one of {allowed}")
        return value.lower()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Normalise log level values while validating allowed options."""

        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"Invalid log level '{value}'. Must be one of {allowed}")
        return upper

    def iter_provider_settings(self) -> dict[str, ProviderSettings]:
        """Return provider settings keyed by provider identifier."""

        return {
            "linkup": self.linkup,
            "exa": self.exa,
            "perplexity": self.perplexity,
            "tavily": self.tavily,
            "firecrawl": self.firecrawl,
        }


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings instance."""

    return AppSettings()


__all__ = [
    "AppSettings",
    "CacheConfig",
    "MiddlewareConfig",
    "ProviderSettings",
    "ResultConfig",
    "RetryConfig",
    "RouterSettings",
    "get_settings",
]
