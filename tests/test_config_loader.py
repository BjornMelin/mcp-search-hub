"""Tests for the standardized configuration loader."""

import os
import tempfile
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from mcp_search_hub.utils.config_loader import (
    ConfigLoader,
    StandardizedSettings,
    ComponentSettings,
    ProviderSettings,
    MiddlewareSettings,
    get_component_settings,
    create_settings_factory,
)


class TestConfigLoader:
    """Test ConfigLoader utility methods."""
    
    def test_parse_comma_separated_list(self):
        """Test parsing comma-separated strings into lists."""
        # Normal case
        result = ConfigLoader.parse_comma_separated_list("a,b,c")
        assert result == ["a", "b", "c"]
        
        # With spaces
        result = ConfigLoader.parse_comma_separated_list("a, b , c")
        assert result == ["a", "b", "c"]
        
        # Empty string
        result = ConfigLoader.parse_comma_separated_list("")
        assert result == []
        
        # Single item
        result = ConfigLoader.parse_comma_separated_list("single")
        assert result == ["single"]
        
        # With empty items
        result = ConfigLoader.parse_comma_separated_list("a,,b,")
        assert result == ["a", "b"]
    
    def test_parse_env_bool(self):
        """Test parsing environment variables as booleans."""
        # True values
        assert ConfigLoader.parse_env_bool("true") is True
        assert ConfigLoader.parse_env_bool("TRUE") is True
        assert ConfigLoader.parse_env_bool("1") is True
        assert ConfigLoader.parse_env_bool("yes") is True
        assert ConfigLoader.parse_env_bool("on") is True
        
        # False values
        assert ConfigLoader.parse_env_bool("false") is False
        assert ConfigLoader.parse_env_bool("0") is False
        assert ConfigLoader.parse_env_bool("no") is False
        
        # Empty/default
        assert ConfigLoader.parse_env_bool("") is False
        assert ConfigLoader.parse_env_bool("", default=True) is True
    
    def test_parse_env_int(self):
        """Test parsing environment variables as integers."""
        assert ConfigLoader.parse_env_int("123") == 123
        assert ConfigLoader.parse_env_int("0") == 0
        assert ConfigLoader.parse_env_int("-5") == -5
        
        # Invalid values return default
        assert ConfigLoader.parse_env_int("invalid") == 0
        assert ConfigLoader.parse_env_int("", default=42) == 42
        assert ConfigLoader.parse_env_int("not_int", default=100) == 100
    
    def test_parse_env_float(self):
        """Test parsing environment variables as floats."""
        assert ConfigLoader.parse_env_float("123.45") == 123.45
        assert ConfigLoader.parse_env_float("0.0") == 0.0
        assert ConfigLoader.parse_env_float("-5.5") == -5.5
        
        # Invalid values return default
        assert ConfigLoader.parse_env_float("invalid") == 0.0
        assert ConfigLoader.parse_env_float("", default=42.0) == 42.0
        assert ConfigLoader.parse_env_float("not_float", default=100.5) == 100.5
    
    @patch.dict(os.environ, {"FIRST_KEY": "first_value", "SECOND_KEY": "second_value"})
    def test_get_env_with_fallback(self):
        """Test getting environment variables with fallback."""
        # Primary key exists
        result = ConfigLoader.get_env_with_fallback("FIRST_KEY", "SECOND_KEY")
        assert result == "first_value"
        
        # Primary key doesn't exist, fallback does
        result = ConfigLoader.get_env_with_fallback("MISSING_KEY", "SECOND_KEY")
        assert result == "second_value"
        
        # Neither exists, use default
        result = ConfigLoader.get_env_with_fallback("MISSING_KEY", "ANOTHER_MISSING", "default")
        assert result == "default"
    
    @patch.dict(os.environ, {
        "TEST_API_KEY": "test_key_123",
        "TEST_ENABLED": "false",
        "TEST_TIMEOUT": "15.5",
        "TEST_MAX_RETRIES": "5"
    })
    def test_load_provider_config(self):
        """Test loading standardized provider configuration."""
        config = ConfigLoader.load_provider_config("test")
        
        assert config["name"] == "test"
        assert config["api_key"] == "test_key_123"
        assert config["enabled"] is False
        assert config["timeout"] == 15.5
        assert config["max_retries"] == 5
    
    @patch.dict(os.environ, {
        "AUTH_MIDDLEWARE_ENABLED": "false",
        "AUTH_MIDDLEWARE_ORDER": "15"
    })
    def test_load_middleware_config(self):
        """Test loading standardized middleware configuration."""
        config = ConfigLoader.load_middleware_config("auth")
        
        assert config["enabled"] is False
        assert config["order"] == 15
    
    @patch.dict(os.environ, {})
    def test_load_config_with_defaults(self):
        """Test loading configuration with default values."""
        config = ConfigLoader.load_provider_config("test")
        
        assert config["name"] == "test"
        assert config["api_key"] == ""
        assert config["enabled"] is True  # Default
        assert config["timeout"] == 30.0  # Default
        assert config["max_retries"] == 3  # Default


class TestStandardizedSettings:
    """Test StandardizedSettings base class."""
    
    def test_standardized_settings_basic(self):
        """Test basic functionality of StandardizedSettings."""
        
        class TestSettings(StandardizedSettings):
            required_field: str
            optional_field: str | None = None
        
        # Test basic instantiation
        settings = TestSettings(required_field="value")
        assert settings.required_field == "value"
        assert settings.optional_field is None
        
        # Test setting optional field
        settings = TestSettings(required_field="value", optional_field="optional")
        assert settings.optional_field == "optional"
    
    def test_env_file_loading(self):
        """Test loading from .env file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("TEST_VALUE=from_env_file\n")
            f.flush()
            
            class TestSettings(StandardizedSettings):
                test_value: str = "default"
                
                model_config = StandardizedSettings.model_config.copy()
                model_config.update({"env_file": f.name})
            
            settings = TestSettings()
            assert settings.test_value == "from_env_file"
        
        os.unlink(f.name)


class TestComponentSettings:
    """Test ComponentSettings class."""
    
    def test_required_name_field(self):
        """Test that name field is required."""
        with pytest.raises(ValidationError):
            ComponentSettings()
    
    def test_default_values(self):
        """Test default values for component settings."""
        settings = ComponentSettings(name="test_component")
        
        assert settings.name == "test_component"
        assert settings.enabled is True
        assert settings.debug is False
    
    @patch.dict(os.environ, {
        "COMPONENT_DEBUG": "true",
        "COMPONENT_ENABLED": "false"
    })
    def test_env_prefix(self):
        """Test that COMPONENT_ prefix is applied correctly."""
        settings = ComponentSettings(name="test")
        
        assert settings.debug is True
        assert settings.enabled is False


class TestProviderSettings:
    """Test ProviderSettings class."""
    
    def test_default_values(self):
        """Test default values for provider settings."""
        settings = ProviderSettings(name="test_provider")
        
        assert settings.name == "test_provider"
        assert settings.api_key == ""
        assert settings.timeout == 30.0
        assert settings.max_retries == 3
    
    @patch.dict(os.environ, {
        "LINKUP_API_KEY": "test_key",
        "LINKUP_ENABLED": "false",
        "LINKUP_TIMEOUT": "10.0",
        "LINKUP_MAX_RETRIES": "5"
    })
    def test_for_provider_class_method(self):
        """Test creating provider settings for specific provider."""
        settings = ProviderSettings.for_provider("linkup")
        
        assert settings.name == "linkup"
        assert settings.api_key == "test_key"
        assert settings.enabled is False
        assert settings.timeout == 10.0
        assert settings.max_retries == 5


class TestMiddlewareSettings:
    """Test MiddlewareSettings class."""
    
    def test_default_values(self):
        """Test default values for middleware settings."""
        settings = MiddlewareSettings(name="test_middleware")
        
        assert settings.name == "test_middleware"
        assert settings.order == 10
    
    @patch.dict(os.environ, {
        "RETRY_MIDDLEWARE_ENABLED": "false",
        "RETRY_MIDDLEWARE_ORDER": "25"
    })
    def test_for_middleware_class_method(self):
        """Test creating middleware settings for specific middleware."""
        settings = MiddlewareSettings.for_middleware("retry")
        
        assert settings.name == "retry"
        assert settings.enabled is False
        assert settings.order == 25


class TestUtilityFunctions:
    """Test utility functions."""
    
    @patch.dict(os.environ, {"TEST_API_KEY": "test_value"})
    def test_get_component_settings_cached(self):
        """Test that component settings are cached properly."""
        # First call
        settings1 = get_component_settings("provider", "test")
        
        # Second call should return the same cached instance
        settings2 = get_component_settings("provider", "test")
        
        assert settings1 is settings2
    
    def test_create_settings_factory(self):
        """Test creating settings factory with custom configuration."""
        CustomSettings = create_settings_factory(
            ComponentSettings,
            env_prefix="CUSTOM_",
            case_sensitive=True
        )
        
        # Should be a subclass of ComponentSettings
        assert issubclass(CustomSettings, ComponentSettings)
        
        # Should have the custom env_prefix
        assert CustomSettings.model_config["env_prefix"] == "CUSTOM_"
        assert CustomSettings.model_config["case_sensitive"] is True


class TestIntegration:
    """Integration tests for configuration loading."""
    
    @patch.dict(os.environ, {
        "LINKUP_API_KEY": "linkup_key",
        "LINKUP_ENABLED": "true",
        "EXA_API_KEY": "exa_key", 
        "EXA_TIMEOUT": "20.0",
        "AUTH_MIDDLEWARE_ORDER": "5"
    })
    def test_full_configuration_loading(self):
        """Test full configuration loading with multiple components."""
        # Load provider settings
        linkup_settings = ProviderSettings.for_provider("linkup")
        exa_settings = ProviderSettings.for_provider("exa")
        
        # Load middleware settings
        auth_settings = MiddlewareSettings.for_middleware("auth")
        
        # Verify provider settings
        assert linkup_settings.api_key == "linkup_key"
        assert linkup_settings.enabled is True
        assert exa_settings.api_key == "exa_key"
        assert exa_settings.timeout == 20.0
        
        # Verify middleware settings
        assert auth_settings.order == 5