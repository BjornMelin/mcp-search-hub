"""Typed application and provider configuration."""

from __future__ import annotations

import os
import re
from decimal import Decimal
from functools import lru_cache
from typing import Any, Literal, cast
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_REFERENCE = re.compile(r"^\$[A-Za-z_][A-Za-z0-9_]*$")
_PROVIDER_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]*$")
_LOCAL_HTTP_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _default_field_aliases() -> dict[str, list[str]]:
    return {
        "title": ["title", "name"],
        "url": ["url", "link"],
        "snippet": ["snippet", "description", "text"],
        "score": ["score", "relevance", "confidence"],
        "raw_content": ["raw_content", "content"],
    }


def resolve_env_references(value: Any) -> Any:
    """Resolve explicit ``$NAME`` references without expanding arbitrary strings."""

    if isinstance(value, str) and _ENV_REFERENCE.fullmatch(value):
        name = value[1:]
        try:
            return os.environ[name]
        except KeyError as exc:
            raise ValueError(
                f"Missing environment variable referenced by provider: {name}"
            ) from exc
    if isinstance(value, dict):
        mapping = cast(dict[str, Any], value)
        return {key: resolve_env_references(item) for key, item in mapping.items()}
    if isinstance(value, list):
        sequence = cast(list[Any], value)
        return [resolve_env_references(item) for item in sequence]
    return value


class StrictModel(BaseModel):
    """Reject misspelled fields in deployment-owned configuration objects."""

    model_config = ConfigDict(extra="forbid")


class RouterSettings(StrictModel):
    """Deterministic routing and query-budget defaults."""

    max_providers: int = Field(default=3, ge=1, le=20)
    default_timeout_seconds: float = Field(default=20.0, gt=0.0, le=300.0)
    default_budget_usd: Decimal | None = Field(default=None, gt=Decimal("0"))


class ResultSettings(StrictModel):
    """Public result limits and fusion settings."""

    max_results: int = Field(default=20, ge=1, le=100)
    reciprocal_rank_k: int = Field(default=60, ge=1, le=1000)


class MiddlewareSettings(StrictModel):
    """Native FastMCP middleware settings."""

    rate_limit_requests: int = Field(default=120, ge=1)
    rate_limit_window_minutes: int = Field(default=1, ge=1, le=1440)
    include_log_payloads: bool = False


class ProviderSettings(StrictModel):
    """Configuration for one generic downstream MCP search provider."""

    enabled: bool = True
    transport: str | dict[str, Any] | None = None
    command: list[str] | None = None
    env: dict[str, str] = Field(default_factory=lambda: dict[str, str]())
    tool: str = Field(default="search", min_length=1)
    tags: set[str] = Field(default_factory=lambda: set[str]())
    weight: float = Field(default=1.0, gt=0.0, allow_inf_nan=False)
    timeout_seconds: float = Field(default=20.0, gt=0.0, le=300.0)
    estimated_cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    query_argument: str = Field(default="query", min_length=1)
    max_results_argument: str | None = "max_results"
    raw_content_argument: str | None = "include_raw_content"
    static_arguments: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    result_path: list[str | int] = Field(default_factory=lambda: ["results"])
    field_aliases: dict[str, list[str]] = Field(default_factory=_default_field_aliases)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: set[str]) -> set[str]:
        return {tag.strip().lower() for tag in value if tag.strip()}

    @field_validator("transport")
    @classmethod
    def validate_transport(cls, value: str | dict[str, Any] | None) -> str | dict[str, Any] | None:
        if isinstance(value, str) and (not value.strip() or value != value.strip()):
            raise ValueError("Provider transport strings must be nonblank and trimmed")
        if isinstance(value, dict) and not value:
            raise ValueError("Provider transport mappings must not be empty")
        return value

    @field_validator(
        "tool",
        "query_argument",
        "max_results_argument",
        "raw_content_argument",
    )
    @classmethod
    def validate_tool_argument_names(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value != value.strip()):
            raise ValueError("Provider tool and argument names must be nonblank and trimmed")
        return value

    @model_validator(mode="after")
    def validate_connection(self) -> ProviderSettings:
        dynamic_arguments = [
            argument
            for argument in (
                self.query_argument,
                self.max_results_argument,
                self.raw_content_argument,
            )
            if argument is not None
        ]
        if len(dynamic_arguments) != len(set(dynamic_arguments)):
            raise ValueError("Provider dynamic argument names must be unique")
        shadowed_arguments = set(dynamic_arguments).intersection(self.static_arguments)
        if shadowed_arguments:
            raise ValueError(
                "Provider static arguments must not shadow dynamic arguments: "
                f"{sorted(shadowed_arguments)}"
            )
        allowed_fields = {"title", "url", "snippet", "score", "raw_content"}
        unknown_fields = set(self.field_aliases) - allowed_fields
        if unknown_fields:
            raise ValueError(f"Unknown result field aliases: {sorted(unknown_fields)}")
        invalid_aliases = {
            field_name: aliases
            for field_name, aliases in self.field_aliases.items()
            if not aliases or any(not alias.strip() or alias != alias.strip() for alias in aliases)
        }
        if invalid_aliases:
            raise ValueError("Result field alias lists must contain nonblank, trimmed names")
        defaults = _default_field_aliases()
        self.field_aliases = {
            field_name: list(dict.fromkeys(self.field_aliases.get(field_name, aliases)))
            for field_name, aliases in defaults.items()
        }
        if not self.enabled:
            return self
        if (self.transport is None) == (self.command is None):
            raise ValueError("Enabled providers require exactly one of transport or command")
        if self.command is not None and (
            not self.command
            or not self.command[0].strip()
            or self.command[0] != self.command[0].strip()
        ):
            raise ValueError("Provider command must contain an executable")
        if self.transport is not None and self.env:
            raise ValueError(
                "Provider env is only valid with command; embed headers or env in transport"
            )
        return self

    def resolved_transport(self, identifier: str) -> Any:
        """Build the FastMCP client transport after resolving explicit secrets."""

        if self.command is not None:
            from fastmcp.client.transports.stdio import StdioTransport

            command = cast(list[str], resolve_env_references(self.command))
            env = resolve_env_references(self.env)
            if not command or not command[0].strip() or command[0] != command[0].strip():
                raise ValueError("Resolved provider command must contain a trimmed executable")
            return StdioTransport(
                command=command[0],
                args=command[1:],
                env=env or None,
                keep_alive=True,
            )
        if self.transport is None:
            raise ValueError(f"Provider {identifier!r} has no transport")
        transport = resolve_env_references(self.transport)
        if isinstance(transport, str) and (not transport.strip() or transport != transport.strip()):
            raise ValueError("Resolved provider transport strings must be nonblank and trimmed")
        return transport


class AppSettings(BaseSettings):
    """Primary application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "MCP Search Hub"
    environment: Literal["development", "test", "staging", "production"] = "development"
    transport: Literal["stdio", "http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65_535)
    http_path: str = "/mcp"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    auth_tokens: list[SecretStr] = Field(default_factory=lambda: list[SecretStr]())
    providers: dict[str, ProviderSettings] = Field(
        default_factory=lambda: dict[str, ProviderSettings]()
    )
    router: RouterSettings = Field(default_factory=RouterSettings)
    results: ResultSettings = Field(default_factory=ResultSettings)
    middleware: MiddlewareSettings = Field(default_factory=MiddlewareSettings)

    @field_validator("http_path")
    @classmethod
    def validate_http_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("HTTP path must start with '/'")
        parsed = urlsplit(value)
        if parsed.path != value or parsed.scheme or parsed.netloc:
            raise ValueError("HTTP path must not contain a query, fragment, or authority")
        decoded_path = unquote(parsed.path)
        if decoded_path != parsed.path:
            raise ValueError("HTTP path must not contain percent-encoded characters")
        if any(segment in {".", ".."} for segment in decoded_path.split("/")):
            raise ValueError("HTTP path must not contain dot segments")
        if decoded_path.rstrip("/") == "/health":
            raise ValueError("HTTP path '/health' is reserved for the health endpoint")
        return value

    @field_validator("auth_tokens")
    @classmethod
    def validate_auth_tokens(cls, value: list[SecretStr]) -> list[SecretStr]:
        tokens = [secret.get_secret_value() for secret in value]
        if any(not token or token != token.strip() for token in tokens):
            raise ValueError("AUTH_TOKENS entries must be nonblank without surrounding whitespace")
        if len(tokens) != len(set(tokens)):
            raise ValueError("AUTH_TOKENS entries must be unique")
        return value

    @field_validator("providers")
    @classmethod
    def validate_provider_identifiers(
        cls, value: dict[str, ProviderSettings]
    ) -> dict[str, ProviderSettings]:
        invalid = [name for name in value if not _PROVIDER_IDENTIFIER.fullmatch(name)]
        if invalid:
            raise ValueError(f"Invalid provider identifiers: {sorted(invalid)}")
        return value

    @model_validator(mode="after")
    def require_auth_for_network_bind(self) -> AppSettings:
        if self.transport == "http":
            self.validate_http_bind()
        return self

    def validate_http_bind(self) -> None:
        """Reject unauthenticated HTTP binds outside the local host."""

        if self.host not in _LOCAL_HTTP_HOSTS and not self.auth_tokens:
            raise ValueError("HTTP network binds require at least one AUTH_TOKENS entry")


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return the process-wide settings instance."""

    return AppSettings()


__all__ = [
    "AppSettings",
    "MiddlewareSettings",
    "ProviderSettings",
    "ResultSettings",
    "RouterSettings",
    "get_settings",
    "resolve_env_references",
]
