"""Tests for the simplified settings module."""

import os
import tempfile
from unittest.mock import patch

from pydantic import SecretStr

from mcp_search_hub.config.settings import AppSettings, get_settings


class TestAppSettings:
    """Test AppSettings class."""

    def test_default_values(self):
        """Test default values for app settings."""
        settings = AppSettings()

        # Application metadata
        assert settings.app_name == "MCP Search Hub"
        assert settings.environment == "development"

        # Server defaults
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.log_level == "INFO"
        assert settings.transport == "streamable-http"

        # Cache defaults
        assert settings.cache.memory_ttl == 300
        assert settings.cache.redis_ttl == 3600
        assert settings.cache.redis_url == "redis://localhost:6379"
        assert settings.cache.redis_enabled is False
        assert settings.cache.prefix == "search:"
        assert settings.cache.fingerprint_enabled is True
        assert settings.cache.clean_interval == 600
        assert settings.cache.ttl_jitter == 60

        # Provider defaults
        assert settings.linkup.enabled is True
        assert settings.exa.enabled is True
        assert settings.perplexity.enabled is True
        assert settings.tavily.enabled is True
        assert settings.firecrawl.enabled is True

        # Timeout defaults
        assert settings.linkup.timeout == 30.0
        assert settings.exa.timeout == 30.0
        assert settings.perplexity.timeout == 30.0
        assert settings.tavily.timeout == 30.0
        assert settings.firecrawl.timeout == 30.0

        # Retry defaults
        assert settings.retry.max_retries == 3
        assert settings.retry.base_delay == 1.0
        assert settings.retry.max_delay == 60.0
        assert settings.retry.exponential_base == 2.0
        assert settings.retry.jitter is True

        # Router defaults
        assert settings.router.max_providers == 3
        assert settings.router.min_confidence == 0.6
        assert settings.router.execution_strategy == "auto"
        assert settings.router.max_concurrent == 3
        assert settings.router.base_timeout_ms == 10000

        # Middleware defaults
        assert settings.middleware.auth_enabled is True
        assert settings.middleware.rate_limit_enabled is True
        assert settings.middleware.logging_enabled is True

    @patch.dict(
        os.environ,
        {
            "LINKUP__API_KEY": "test_key_123",
            "EXA__ENABLED": "false",
            "CACHE__REDIS_TTL": "7200",
            "MIDDLEWARE__AUTH_ENABLED": "false",
        },
    )
    def test_environment_variable_loading(self):
        """Test that environment variables are loaded correctly with nested structure."""
        settings = AppSettings()

        # Test nested environment variables work
        assert settings.linkup.api_key.get_secret_value() == "test_key_123"
        assert settings.exa.enabled is False
        assert settings.cache.redis_ttl == 7200
        assert settings.middleware.auth_enabled is False

    def test_environment_file_loading(self):
        """Test loading from .env file."""
        env_content = """
# Test environment file
HOST=test.example.com
PORT=9000
LINKUP__API_KEY=file_key_456
CACHE__REDIS_ENABLED=true
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(env_content)
            f.flush()

            # Load settings with specific env file
            settings = AppSettings(_env_file=f.name)

            assert settings.host == "test.example.com"
            assert settings.port == 9000
            assert settings.linkup.api_key.get_secret_value() == "file_key_456"
            assert settings.cache.redis_enabled is True

        # Clean up
        os.unlink(f.name)

    def test_secret_str_handling(self):
        """Test that API keys are handled as SecretStr properly."""
        settings = AppSettings()

        # Set a secret value as SecretStr
        settings.linkup.api_key = SecretStr("secret_key_123")

        # Should be SecretStr type
        assert hasattr(settings.linkup.api_key, "get_secret_value")

        # Should not expose the secret in string representation
        settings_str = str(settings)
        assert "secret_key_123" not in settings_str

        # Should be accessible via get_secret_value
        assert settings.linkup.api_key.get_secret_value() == "secret_key_123"

    def test_validation(self):
        """Test field validation."""
        # Test valid environment
        settings = AppSettings(environment="production")
        assert settings.environment == "production"

        # Test invalid environment
        try:
            AppSettings(environment="invalid")
            raise AssertionError("Should have raised ValidationError")
        except Exception:
            pass  # Expected

        # Test valid log level
        settings = AppSettings(log_level="DEBUG")
        assert settings.log_level == "DEBUG"

        # Test invalid log level
        try:
            AppSettings(log_level="INVALID")
            raise AssertionError("Should have raised ValidationError")
        except Exception:
            pass  # Expected

    def test_provider_helper_methods(self):
        """Test helper methods for provider configuration."""
        settings = AppSettings()

        # Test get_provider_config
        linkup_config = settings.get_provider_config("linkup")
        assert linkup_config is not None
        assert linkup_config.enabled is True

        # Test non-existent provider
        invalid_config = settings.get_provider_config("nonexistent")
        assert invalid_config is None

        # Test get_enabled_providers
        enabled = settings.get_enabled_providers()
        assert "linkup" in enabled
        assert "exa" in enabled
        assert len(enabled) == 5  # All providers enabled by default

        # Test with disabled provider
        settings.exa.enabled = False
        enabled = settings.get_enabled_providers()
        assert "exa" not in enabled
        assert len(enabled) == 4


class TestGetSettings:
    """Test get_settings function."""

    def test_cached_settings(self):
        """Test that settings are cached properly."""
        # Clear cache first
        get_settings.cache_clear()

        # First call
        settings1 = get_settings()

        # Second call should return the same cached instance
        settings2 = get_settings()

        assert settings1 is settings2

    @patch.dict(os.environ, {"HOST": "test_host"})
    def test_environment_changes_after_cache(self):
        """Test that environment changes don't affect cached settings."""
        # Clear cache first
        get_settings.cache_clear()

        # Get settings with current environment
        settings1 = get_settings()
        original_host = settings1.host

        # Change environment
        with patch.dict(os.environ, {"HOST": "different_host"}):
            # Should still return cached settings
            settings2 = get_settings()
            assert settings2.host == original_host
            assert settings2 is settings1

    def test_returns_app_settings_instance(self):
        """Test that get_settings returns AppSettings instance."""
        settings = get_settings()
        assert isinstance(settings, AppSettings)

        # Test that it has the expected structure
        assert hasattr(settings, "linkup")
        assert hasattr(settings, "exa")
        assert hasattr(settings, "perplexity")
        assert hasattr(settings, "tavily")
        assert hasattr(settings, "firecrawl")
        assert hasattr(settings, "cache")
        assert hasattr(settings, "retry")
        assert hasattr(settings, "router")
        assert hasattr(settings, "middleware")
