"""Tests for the standardized settings module."""

import os
import tempfile
from unittest.mock import patch

from mcp_search_hub.config.settings import AppSettings, get_app_settings, get_settings
from mcp_search_hub.models.config import Settings


class TestAppSettings:
    """Test AppSettings class."""

    def test_default_values(self):
        """Test default values for app settings."""
        settings = AppSettings()

        # Server defaults
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.log_level == "INFO"
        assert settings.transport == "streamable-http"

        # Cache defaults
        assert settings.cache_ttl == 3600
        assert settings.cache_memory_ttl == 300
        assert settings.cache_redis_ttl == 3600
        assert settings.redis_url == "redis://localhost:6379"
        assert settings.redis_enabled is False
        assert settings.cache_prefix == "search:"
        assert settings.cache_fingerprint_enabled is True
        assert settings.cache_clean_interval == 600

        # Provider defaults
        assert settings.linkup_enabled is True
        assert settings.exa_enabled is True
        assert settings.perplexity_enabled is True
        assert settings.tavily_enabled is True
        assert settings.firecrawl_enabled is True

        # Timeout defaults
        assert settings.linkup_timeout == 5.0
        assert settings.exa_timeout == 5.0
        assert settings.perplexity_timeout == 5.0
        assert settings.tavily_timeout == 5.0
        assert settings.firecrawl_timeout == 5.0

        # Retry defaults
        assert settings.max_retries == 3
        assert settings.retry_base_delay == 1.0
        assert settings.retry_max_delay == 60.0
        assert settings.retry_exponential_base == 2.0
        assert settings.retry_jitter is True

        # Rate limit defaults
        assert settings.rate_limit == 100
        assert settings.rate_limit_window == 60
        assert settings.global_rate_limit == 1000
        assert settings.global_rate_limit_window == 60

        # Logging defaults
        assert settings.logging_include_headers is True
        assert settings.logging_include_body is False
        assert settings.logging_max_body_size == 1024

    @patch.dict(
        os.environ,
        {
            "HOST": "127.0.0.1",
            "PORT": "9000",
            "LOG_LEVEL": "DEBUG",
            "LINKUP_API_KEY": "test_linkup_key",
            "EXA_ENABLED": "false",
            "PERPLEXITY_TIMEOUT": "15.0",
            "CACHE_MEMORY_TTL": "600",
            "REDIS_ENABLED": "true",
            "MAX_RETRIES": "5",
            "RATE_LIMIT": "200",
        },
    )
    def test_environment_variable_loading(self):
        """Test loading settings from environment variables."""
        settings = AppSettings()

        # Server settings
        assert settings.host == "127.0.0.1"
        assert settings.port == 9000
        assert settings.log_level == "DEBUG"

        # Provider settings
        assert settings.linkup_api_key.get_secret_value() == "test_linkup_key"
        assert settings.exa_enabled is False
        assert settings.perplexity_timeout == 15.0

        # Cache settings
        assert settings.cache_memory_ttl == 600
        assert settings.redis_enabled is True

        # Other settings
        assert settings.max_retries == 5
        assert settings.rate_limit == 200

    def test_env_file_loading(self):
        """Test loading settings from .env file."""
        env_content = """
HOST=192.168.1.1
PORT=7000
LINKUP_API_KEY=env_file_key
EXA_ENABLED=false
CACHE_PREFIX=test:
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(env_content)
            f.flush()

            # Create settings with custom env file
            settings = AppSettings(_env_file=f.name)

            assert settings.host == "192.168.1.1"
            assert settings.port == 7000
            assert settings.linkup_api_key.get_secret_value() == "env_file_key"
            assert settings.exa_enabled is False
            assert settings.cache_prefix == "test:"

        os.unlink(f.name)

    def test_to_legacy_settings(self):
        """Test conversion to legacy Settings format."""
        app_settings = AppSettings(
            auth_api_keys="key1,key2,key3",
            auth_skip_paths="/skip1,/skip2",
            sensitive_headers="header1,header2",
        )

        legacy_settings = app_settings.to_legacy_settings()

        # Check that it's the correct type
        assert isinstance(legacy_settings, Settings)

        # Check that comma-separated values are parsed correctly
        assert legacy_settings.middleware.auth.api_keys == ["key1", "key2", "key3"]
        assert legacy_settings.middleware.auth.skip_auth_paths == ["/skip1", "/skip2"]
        assert legacy_settings.middleware.logging.sensitive_headers == [
            "header1",
            "header2",
        ]

        # Check provider configuration
        assert legacy_settings.providers.linkup.enabled is True
        assert legacy_settings.providers.exa.enabled is True

        # Check cache configuration
        assert legacy_settings.cache.memory_ttl == 300
        assert legacy_settings.cache.redis_enabled is False

    def test_secret_str_handling(self):
        """Test that API keys are handled as SecretStr properly."""
        settings = AppSettings(linkup_api_key="secret_key_123")

        # Should be SecretStr type
        assert hasattr(settings.linkup_api_key, "get_secret_value")

        # Should not expose the secret in string representation
        settings_str = str(settings)
        assert "secret_key_123" not in settings_str

        # Should be accessible via get_secret_value
        assert settings.linkup_api_key.get_secret_value() == "secret_key_123"


class TestGetAppSettings:
    """Test get_app_settings function."""

    def test_cached_settings(self):
        """Test that settings are cached properly."""
        # Clear cache first
        get_app_settings.cache_clear()

        # First call
        settings1 = get_app_settings()

        # Second call should return the same cached instance
        settings2 = get_app_settings()

        assert settings1 is settings2

    @patch.dict(os.environ, {"HOST": "test_host"})
    def test_environment_changes_after_cache(self):
        """Test that environment changes don't affect cached settings."""
        # Clear cache first
        get_app_settings.cache_clear()

        # Get settings with current environment
        settings1 = get_app_settings()
        original_host = settings1.host

        # Change environment
        with patch.dict(os.environ, {"HOST": "different_host"}):
            # Should still return cached settings
            settings2 = get_app_settings()
            assert settings2.host == original_host
            assert settings2 is settings1


class TestGetSettings:
    """Test get_settings function (legacy compatibility)."""

    def test_returns_legacy_settings_type(self):
        """Test that get_settings returns legacy Settings type."""
        settings = get_settings()

        assert isinstance(settings, Settings)

        # Test that it has the expected structure
        assert hasattr(settings, "providers")
        assert hasattr(settings, "middleware")
        assert hasattr(settings, "cache")

        # Test provider structure
        assert hasattr(settings.providers, "linkup")
        assert hasattr(settings.providers, "exa")
        assert hasattr(settings.providers, "perplexity")
        assert hasattr(settings.providers, "tavily")
        assert hasattr(settings.providers, "firecrawl")

        # Test middleware structure
        assert hasattr(settings.middleware, "auth")
        assert hasattr(settings.middleware, "logging")
        assert hasattr(settings.middleware, "rate_limit")
        assert hasattr(settings.middleware, "retry")

    def test_cached_legacy_settings(self):
        """Test that legacy settings are cached properly."""
        # Clear cache first
        get_settings.cache_clear()

        # First call
        settings1 = get_settings()

        # Second call should return the same cached instance
        settings2 = get_settings()

        assert settings1 is settings2

    @patch.dict(
        os.environ,
        {
            "LINKUP_API_KEY": "test_key",
            "EXA_ENABLED": "false",
            "AUTH_API_KEYS": "key1,key2",
        },
    )
    def test_legacy_settings_with_env_vars(self):
        """Test legacy settings loading with environment variables."""
        # Clear cache to ensure fresh load
        get_settings.cache_clear()
        get_app_settings.cache_clear()

        settings = get_settings()

        # Test provider settings
        assert settings.providers.linkup.api_key.get_secret_value() == "test_key"
        assert settings.providers.exa.enabled is False

        # Test middleware settings (should parse comma-separated values)
        assert settings.middleware.auth.api_keys == ["key1", "key2"]


class TestIntegration:
    """Integration tests for the standardized settings system."""

    @patch.dict(
        os.environ,
        {
            "HOST": "production.example.com",
            "PORT": "8080",
            "LOG_LEVEL": "WARNING",
            "LINKUP_API_KEY": "prod_linkup_key",
            "EXA_API_KEY": "prod_exa_key",
            "PERPLEXITY_API_KEY": "prod_perplexity_key",
            "TAVILY_API_KEY": "prod_tavily_key",
            "FIRECRAWL_API_KEY": "prod_firecrawl_key",
            "REDIS_ENABLED": "true",
            "REDIS_URL": "redis://production-redis:6379",
            "CACHE_PREFIX": "prod:",
            "MAX_RETRIES": "5",
            "RATE_LIMIT": "500",
            "AUTH_API_KEYS": "prod_key1,prod_key2,prod_key3",
            "SENSITIVE_HEADERS": "authorization,x-api-key,x-custom-header",
        },
    )
    def test_production_like_configuration(self):
        """Test loading production-like configuration."""
        # Clear caches
        get_settings.cache_clear()
        get_app_settings.cache_clear()

        # Get both app settings and legacy settings
        app_settings = get_app_settings()
        legacy_settings = get_settings()

        # Test app settings
        assert app_settings.host == "production.example.com"
        assert app_settings.port == 8080
        assert app_settings.log_level == "WARNING"
        assert app_settings.redis_enabled is True
        assert app_settings.redis_url == "redis://production-redis:6379"
        assert app_settings.cache_prefix == "prod:"
        assert app_settings.max_retries == 5
        assert app_settings.rate_limit == 500

        # Test provider API keys
        assert app_settings.linkup_api_key.get_secret_value() == "prod_linkup_key"
        assert app_settings.exa_api_key.get_secret_value() == "prod_exa_key"
        assert (
            app_settings.perplexity_api_key.get_secret_value() == "prod_perplexity_key"
        )
        assert app_settings.tavily_api_key.get_secret_value() == "prod_tavily_key"
        assert app_settings.firecrawl_api_key.get_secret_value() == "prod_firecrawl_key"

        # Test legacy settings equivalence
        assert legacy_settings.host == app_settings.host
        assert legacy_settings.port == app_settings.port
        assert legacy_settings.log_level == app_settings.log_level
        assert legacy_settings.cache.redis_enabled == app_settings.redis_enabled
        assert legacy_settings.cache.redis_url == app_settings.redis_url
        assert legacy_settings.cache.prefix == app_settings.cache_prefix

        # Test parsed comma-separated values in legacy settings
        assert legacy_settings.middleware.auth.api_keys == [
            "prod_key1",
            "prod_key2",
            "prod_key3",
        ]
        assert legacy_settings.middleware.logging.sensitive_headers == [
            "authorization",
            "x-api-key",
            "x-custom-header",
        ]
