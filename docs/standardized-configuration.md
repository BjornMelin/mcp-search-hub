# Standardized Configuration Loading

This document describes the standardized configuration loading system implemented in MCP Search Hub. The new system eliminates code duplication, follows modern Pydantic patterns, and provides a consistent interface for configuration management.

## Overview

The standardized configuration system introduces:

1. **ConfigLoader**: A centralized utility class for common configuration patterns
2. **StandardizedSettings**: Base settings class with consistent validation
3. **Component-specific settings**: Specialized settings classes for providers and middleware
4. **Factory pattern**: Flexible configuration class creation
5. **Backward compatibility**: Seamless integration with existing code

## Key Features

### KISS Principle Implementation

The new system follows the KISS (Keep It Simple, Stupid) principle by:

- **Eliminating code duplication**: Common patterns are centralized in `ConfigLoader`
- **Reducing complexity**: Repetitive environment variable parsing is standardized
- **Simplifying maintenance**: Single source of truth for configuration patterns
- **Improving readability**: Clear, consistent interfaces across all components

### Standardized Patterns

#### Environment Variable Parsing

```python
from mcp_search_hub.utils.config_loader import ConfigLoader

# Parse comma-separated lists
paths = ConfigLoader.parse_comma_separated_list("path1,path2,path3")
# Result: ["path1", "path2", "path3"]

# Parse boolean values
enabled = ConfigLoader.parse_env_bool("true")
# Result: True

# Parse numeric values with defaults
timeout = ConfigLoader.parse_env_float("30.5", default=10.0)
# Result: 30.5
```

#### Provider Configuration

```python
from mcp_search_hub.utils.config_loader import ProviderSettings

# Create provider settings for a specific provider
linkup_settings = ProviderSettings.for_provider("linkup")
# Automatically loads LINKUP_API_KEY, LINKUP_ENABLED, etc.
```

#### Middleware Configuration

```python
from mcp_search_hub.utils.config_loader import MiddlewareSettings

# Create middleware settings for a specific middleware
auth_settings = MiddlewareSettings.for_middleware("auth")
# Automatically loads AUTH_MIDDLEWARE_ENABLED, AUTH_MIDDLEWARE_ORDER, etc.
```

### Modern Pydantic Patterns

The system leverages Pydantic 2.0+ features:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from mcp_search_hub.utils.config_loader import StandardizedSettings

class MySettings(StandardizedSettings):
    api_key: str = Field("", description="API key")
    timeout: float = Field(30.0, description="Timeout in seconds")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MY_APP_",
        case_sensitive=False,
    )
```

## Architecture

### ConfigLoader Class

The `ConfigLoader` class provides static methods for common configuration patterns:

- `parse_comma_separated_list()`: Parse comma-separated strings
- `parse_env_bool()`: Parse boolean environment variables
- `parse_env_int()` / `parse_env_float()`: Parse numeric values with error handling
- `get_env_with_fallback()`: Get environment variables with fallback keys
- `load_provider_config()`: Load standardized provider configuration
- `load_middleware_config()`: Load standardized middleware configuration

### Settings Hierarchy

```
StandardizedSettings (base)
├── ComponentSettings (components with name, enabled, debug)
│   ├── ProviderSettings (adds api_key, timeout, max_retries)
│   └── MiddlewareSettings (adds order)
└── AppSettings (main application settings)
```

### Configuration Sources

The system supports multiple configuration sources in order of precedence:

1. **Direct instantiation arguments** (highest priority)
2. **Environment variables**
3. **`.env` files**
4. **Default values** (lowest priority)

## Usage Examples

### Basic Configuration

```python
from mcp_search_hub.config import get_settings

# Get application settings (legacy format for backward compatibility)
settings = get_settings()

# Access provider configuration
linkup_config = settings.providers.linkup
print(f"Linkup enabled: {linkup_config.enabled}")
print(f"Linkup timeout: {linkup_config.timeout}")
```

### Modern Configuration

```python
from mcp_search_hub.config import get_app_settings

# Get modern application settings
app_settings = get_app_settings()

# Access configuration directly
print(f"Host: {app_settings.host}")
print(f"Port: {app_settings.port}")
print(f"Linkup API Key: {app_settings.linkup_api_key.get_secret_value()}")
```

### Environment Variables

Set environment variables to configure the application:

```bash
# Server configuration
export HOST=192.168.1.100
export PORT=9000
export LOG_LEVEL=DEBUG

# Provider configuration
export LINKUP_API_KEY=your_api_key_here
export LINKUP_ENABLED=true
export LINKUP_TIMEOUT=10.0

# Middleware configuration
export AUTH_MIDDLEWARE_ENABLED=true
export AUTH_API_KEYS=key1,key2,key3
export RATE_LIMIT=200
export RATE_LIMIT_WINDOW=60
```

### .env File Support

Create a `.env` file in your project root:

```dotenv
# Server settings
HOST=localhost
PORT=8000
LOG_LEVEL=INFO

# Provider settings
LINKUP_API_KEY=your_linkup_key
EXA_API_KEY=your_exa_key
PERPLEXITY_API_KEY=your_perplexity_key

# Cache settings
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379
CACHE_PREFIX=search:

# Security settings
AUTH_API_KEYS=api_key_1,api_key_2
SENSITIVE_HEADERS=authorization,x-api-key
```

## Migration Guide

### From Legacy Configuration

The new system maintains full backward compatibility. Existing code continues to work without changes:

```python
# This continues to work exactly as before
from mcp_search_hub.config import get_settings

settings = get_settings()
# All existing settings are available in the same structure
```

### To Modern Configuration

To use the new modern configuration system:

```python
# New approach - more direct and type-safe
from mcp_search_hub.config import get_app_settings

app_settings = get_app_settings()
# Access settings directly without nested structures
```

### Custom Settings Classes

Create custom settings classes using the standardized patterns:

```python
from mcp_search_hub.utils.config_loader import (
    StandardizedSettings,
    create_settings_factory
)

# Method 1: Direct inheritance
class CustomSettings(StandardizedSettings):
    my_field: str = Field("default", description="My custom field")
    
    model_config = SettingsConfigDict(
        env_prefix="CUSTOM_",
        env_file="custom.env",
    )

# Method 2: Factory pattern
CustomSettings = create_settings_factory(
    StandardizedSettings,
    env_prefix="CUSTOM_",
    env_file="custom.env"
)
```

## Benefits

### Code Reduction

The new system eliminates approximately 130+ lines of repetitive code from the original `config.py` file by:

- Consolidating common parsing patterns
- Removing duplicate environment variable handling
- Standardizing configuration creation across components

### Improved Maintainability

- **Single source of truth**: Configuration patterns are centralized
- **Type safety**: Full Pydantic validation and type hints
- **Clear interfaces**: Consistent patterns across all components
- **Easy testing**: Standardized mocking and testing approaches

### Enhanced Developer Experience

- **Better IDE support**: Full type hints and autocompletion
- **Clear documentation**: Field descriptions and validation rules
- **Flexible configuration**: Multiple sources with clear precedence
- **Error handling**: Meaningful validation errors with context

## Testing

The system includes comprehensive tests covering:

- Configuration loading from multiple sources
- Environment variable parsing and validation
- Backward compatibility with legacy systems
- Error handling and edge cases
- Integration scenarios

Run the tests:

```bash
# Test the new configuration system
uv run pytest tests/test_config_loader.py
uv run pytest tests/test_standardized_settings.py

# Test integration with existing system
uv run pytest tests/ -k "config"
```

## Future Enhancements

The standardized configuration system provides a foundation for future improvements:

1. **Configuration validation**: Enhanced validation rules and custom validators
2. **Dynamic configuration**: Hot-reloading of configuration changes
3. **Configuration templating**: Support for configuration templates and inheritance
4. **Advanced sources**: Integration with external configuration services
5. **Configuration documentation**: Auto-generated configuration documentation

## Conclusion

The standardized configuration loading system successfully implements the KISS principle while providing a robust, maintainable foundation for configuration management in MCP Search Hub. It eliminates code duplication, follows modern best practices, and maintains full backward compatibility.

The system's design ensures that future configuration needs can be addressed through consistent, well-tested patterns rather than ad-hoc implementations.