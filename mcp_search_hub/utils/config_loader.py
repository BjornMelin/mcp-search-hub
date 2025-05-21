"""Centralized configuration loading utilities.

This module provides a standardized configuration loader that eliminates
code duplication and follows modern Pydantic patterns for configuration
management.
"""

import os
from functools import cache
from typing import Any, TypeVar

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

T = TypeVar("T", bound=BaseModel)


class ConfigLoader:
    """Centralized configuration loader with standardized patterns."""

    @staticmethod
    def parse_comma_separated_list(value: str) -> list[str]:
        """Parse comma-separated string into list of strings."""
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def parse_env_bool(value: str, default: bool = False) -> bool:
        """Parse environment variable as boolean."""
        if not value:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    @staticmethod
    def parse_env_int(value: str, default: int = 0) -> int:
        """Parse environment variable as integer."""
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def parse_env_float(value: str, default: float = 0.0) -> float:
        """Parse environment variable as float."""
        if not value:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    @staticmethod
    def get_env_with_fallback(
        primary_key: str, fallback_key: str | None = None, default: str = ""
    ) -> str:
        """Get environment variable with optional fallback key."""
        value = os.getenv(primary_key)
        if value is not None:
            return value
        if fallback_key:
            value = os.getenv(fallback_key)
            if value is not None:
                return value
        return default

    @staticmethod
    def load_provider_config(provider_name: str) -> dict[str, Any]:
        """Load standardized provider configuration."""
        provider_upper = provider_name.upper()

        return {
            "name": provider_name,
            "api_key": os.getenv(f"{provider_upper}_API_KEY", ""),
            "enabled": ConfigLoader.parse_env_bool(
                os.getenv(f"{provider_upper}_ENABLED", "true")
            ),
            "timeout": ConfigLoader.parse_env_float(
                os.getenv(f"{provider_upper}_TIMEOUT", "30.0")
            ),
            "max_retries": ConfigLoader.parse_env_int(
                os.getenv(f"{provider_upper}_MAX_RETRIES", "3")
            ),
        }

    @staticmethod
    def load_middleware_config(middleware_name: str) -> dict[str, Any]:
        """Load standardized middleware configuration."""
        middleware_upper = f"{middleware_name.upper()}_MIDDLEWARE"

        return {
            "enabled": ConfigLoader.parse_env_bool(
                os.getenv(f"{middleware_upper}_ENABLED", "true")
            ),
            "order": ConfigLoader.parse_env_int(
                os.getenv(f"{middleware_upper}_ORDER", "10")
            ),
        }


class StandardizedSettings(BaseSettings):
    """Base settings class with standardized configuration patterns."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        validate_assignment=True,
    )


class ComponentSettings(StandardizedSettings):
    """Base settings for component configuration."""

    name: str = Field(..., description="Component name")
    enabled: bool = Field(True, description="Whether component is enabled")
    debug: bool = Field(False, description="Enable debug mode")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        validate_assignment=True,
        env_prefix="COMPONENT_",
    )


class ProviderSettings(ComponentSettings):
    """Standardized provider settings."""

    api_key: str = Field("", description="Provider API key")
    timeout: float = Field(30.0, description="Request timeout in seconds")
    max_retries: int = Field(3, description="Maximum retry attempts")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        validate_assignment=True,
        env_prefix="",  # No prefix by default, providers use their own names
    )

    @classmethod
    def for_provider(cls, provider_name: str) -> "ProviderSettings":
        """Create provider settings for specific provider."""
        config = ConfigLoader.load_provider_config(provider_name)
        return cls(**config)


class MiddlewareSettings(ComponentSettings):
    """Standardized middleware settings."""

    order: int = Field(10, description="Middleware execution order")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        validate_assignment=True,
        env_prefix="",  # No prefix by default, middleware use their own patterns
    )

    @classmethod
    def for_middleware(cls, middleware_name: str) -> "MiddlewareSettings":
        """Create middleware settings for specific middleware."""
        config = ConfigLoader.load_middleware_config(middleware_name)
        return cls(name=middleware_name, **config)


@cache
def get_component_settings(
    component_type: str,
    component_name: str,
    settings_class: type[T] = ComponentSettings,
) -> T:
    """Get cached component settings."""
    if component_type == "provider":
        return ProviderSettings.for_provider(component_name)
    if component_type == "middleware":
        return MiddlewareSettings.for_middleware(component_name)
    return settings_class(name=component_name)


def create_settings_factory(
    base_class: type[T], env_prefix: str = "", **default_config
) -> type[T]:
    """Create a settings factory for consistent configuration loading."""

    # Start with base configuration
    config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_nested_delimiter": "__",
        "case_sensitive": False,
        "extra": "ignore",
        "validate_assignment": True,
        "env_prefix": env_prefix,
    }

    # Update with default_config, allowing overrides
    config.update(default_config)

    class FactorySettings(base_class):
        model_config = SettingsConfigDict(**config)

    return FactorySettings
