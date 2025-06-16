# Configuration Guide

This guide covers all configuration options available in MCP Search Hub, from basic setup to advanced optimization.

## Table of Contents

- [Configuration Overview](#configuration-overview)
- [Environment Variables](#environment-variables)
- [Provider Configuration](#provider-configuration)
- [Server Settings](#server-settings)
- [Caching Configuration](#caching-configuration)
- [Middleware Configuration](#middleware-configuration)
- [Performance Tuning](#performance-tuning)
- [Production Settings](#production-settings)
- [Troubleshooting](#troubleshooting)

## Configuration Overview

MCP Search Hub uses environment variables for configuration, following the [12-factor app methodology](https://12factor.net/config). Configuration can be set via:

1. **`.env` file** (recommended for development)
2. **System environment variables** (recommended for production)
3. **Docker environment** (for containerized deployments)

### Configuration Hierarchy

Settings are applied in this order (later overrides earlier):
1. Default values in code
2. `.env` file in project root
3. System environment variables
4. Docker environment variables

## Environment Variables

### Core Server Settings

```bash
# Server Configuration
HOST=0.0.0.0                    # Server bind address (0.0.0.0 for all interfaces)
PORT=8000                       # Server port
LOG_LEVEL=INFO                  # Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
TRANSPORT=http                  # Transport method: "http" or "stdio"

# Application Settings
DEFAULT_BUDGET=0.1              # Default query budget in USD
MAX_CONCURRENT_REQUESTS=10      # Maximum concurrent provider requests
REQUEST_TIMEOUT=30              # Default request timeout in seconds
```

### Provider API Keys

```bash
# Search Provider API Keys (at least one required)
LINKUP_API_KEY=your_linkup_key              # Linkup Search API key
EXA_API_KEY=your_exa_key                    # Exa AI API key
PERPLEXITY_API_KEY=your_perplexity_key      # Perplexity API key
TAVILY_API_KEY=your_tavily_key              # Tavily API key
FIRECRAWL_API_KEY=your_firecrawl_key        # Firecrawl API key
```

### Provider Control

```bash
# Provider Enablement (default: true for providers with API keys)
LINKUP_ENABLED=true             # Enable/disable Linkup provider
EXA_ENABLED=true                # Enable/disable Exa provider
PERPLEXITY_ENABLED=true         # Enable/disable Perplexity provider
TAVILY_ENABLED=true             # Enable/disable Tavily provider
FIRECRAWL_ENABLED=true          # Enable/disable Firecrawl provider

# Provider Timeouts (in milliseconds)
LINKUP_TIMEOUT=10000            # Linkup request timeout
EXA_TIMEOUT=15000               # Exa request timeout
PERPLEXITY_TIMEOUT=20000        # Perplexity request timeout
TAVILY_TIMEOUT=10000            # Tavily request timeout
FIRECRAWL_TIMEOUT=30000         # Firecrawl request timeout
```

## Provider Configuration

Each provider has specific configuration options for API limits, budgets, and behavior.

### Rate Limiting

Configure per-provider rate limits:

```bash
# Rate Limits (example for EXA provider)
EXA_REQUESTS_PER_MINUTE=60      # Maximum requests per minute
EXA_REQUESTS_PER_HOUR=500       # Maximum requests per hour
EXA_REQUESTS_PER_DAY=5000       # Maximum requests per day
EXA_CONCURRENT_REQUESTS=10      # Maximum concurrent requests
EXA_COOLDOWN_PERIOD=5           # Seconds to wait when rate limited
```

Apply the same pattern for other providers: `LINKUP_*`, `PERPLEXITY_*`, `TAVILY_*`, `FIRECRAWL_*`.

### Budget Management

Set spending limits per provider:

```bash
# Budget Configuration (example for EXA provider)
EXA_DEFAULT_QUERY_BUDGET=0.02   # Maximum cost per query in USD
EXA_DAILY_BUDGET=10.00          # Maximum daily spending in USD
EXA_MONTHLY_BUDGET=150.00       # Maximum monthly spending in USD
EXA_ENFORCE_BUDGET=true         # Whether to enforce budget limits
EXA_BASE_COST=0.01              # Base cost per query for calculations
```

### Provider Weights

Control how results are ranked and selected:

```bash
# Provider Selection Weights (0.0 to 1.0, higher = preferred)
LINKUP_WEIGHT=0.9               # High weight for factual accuracy
EXA_WEIGHT=0.85                 # High weight for academic content
PERPLEXITY_WEIGHT=0.8           # Good for current events
TAVILY_WEIGHT=0.75              # RAG-optimized results
FIRECRAWL_WEIGHT=0.7            # Specialized for web scraping
```

## Server Settings

### HTTP Server Configuration

```bash
# HTTP Server Settings
SERVER_WORKERS=1                # Number of worker processes (usually 1 for MCP)
KEEP_ALIVE_TIMEOUT=30           # Keep-alive timeout in seconds
MAX_REQUEST_SIZE=10485760       # Maximum request size (10MB)
GRACEFUL_SHUTDOWN_TIMEOUT=30    # Graceful shutdown timeout
```

### Security Settings

```bash
# Security Configuration
CORS_ENABLED=true               # Enable CORS headers
CORS_ORIGINS=*                  # Allowed CORS origins (comma-separated)
RATE_LIMIT_ENABLED=true         # Enable global rate limiting
RATE_LIMIT_REQUESTS=100         # Requests per window
RATE_LIMIT_WINDOW=60            # Rate limit window in seconds
```

## Caching Configuration

MCP Search Hub supports multiple caching strategies for improved performance.

### Memory Cache

```bash
# Memory Cache Settings
CACHE_TTL=300                   # Legacy cache TTL in seconds
CACHE_MEMORY_TTL=300            # Memory cache TTL (5 minutes)
CACHE_MAX_SIZE=1000             # Maximum items in memory cache
CACHE_CLEAN_INTERVAL=600        # Cache cleanup interval (10 minutes)
```

### Redis Cache (Optional)

```bash
# Redis Configuration
REDIS_CACHE_ENABLED=false       # Enable Redis caching
REDIS_URL=redis://localhost:6379  # Redis connection URL
REDIS_TTL=3600                  # Redis cache TTL (1 hour)
REDIS_PREFIX=search:            # Prefix for Redis cache keys
REDIS_MAX_CONNECTIONS=10        # Maximum Redis connections
REDIS_RETRY_ON_TIMEOUT=true     # Retry Redis operations on timeout
```

### Advanced Caching

```bash
# Advanced Cache Features
CACHE_FINGERPRINT_ENABLED=true  # Enable semantic fingerprinting for queries
CACHE_COMPRESSION_ENABLED=true  # Enable cache data compression
CACHE_STATS_ENABLED=true        # Enable cache statistics tracking
```

## Middleware Configuration

Configure middleware components that handle cross-cutting concerns.

### Logging Middleware

```bash
# Logging Middleware
MIDDLEWARE_LOGGING_ENABLED=true         # Enable logging middleware
MIDDLEWARE_LOGGING_ORDER=5              # Execution order (lower runs first)
MIDDLEWARE_LOGGING_LOG_LEVEL=INFO       # Log level for middleware
MIDDLEWARE_LOGGING_INCLUDE_HEADERS=true # Include headers in logs
MIDDLEWARE_LOGGING_INCLUDE_BODY=false   # Include request/response bodies
MIDDLEWARE_LOGGING_MAX_BODY_SIZE=1024   # Maximum body size to log
```

### Authentication Middleware

```bash
# Authentication Middleware
MIDDLEWARE_AUTH_ENABLED=false           # Enable authentication middleware
MIDDLEWARE_AUTH_ORDER=10                # Execution order
MIDDLEWARE_AUTH_API_KEY=your_api_key    # API key for authentication
MIDDLEWARE_AUTH_HEADER=X-API-Key        # Header name for API key
```

### Rate Limiting Middleware

```bash
# Rate Limiting Middleware
MIDDLEWARE_RATE_LIMIT_ENABLED=true      # Enable rate limiting middleware
MIDDLEWARE_RATE_LIMIT_ORDER=20          # Execution order
MIDDLEWARE_RATE_LIMIT_LIMIT=100         # Requests per window per client
MIDDLEWARE_RATE_LIMIT_WINDOW=60         # Window in seconds
MIDDLEWARE_RATE_LIMIT_GLOBAL_LIMIT=1000 # Global requests per window
```

### Error Handling Middleware

```bash
# Error Handling Middleware
MIDDLEWARE_ERROR_ENABLED=true           # Enable error handling middleware
MIDDLEWARE_ERROR_ORDER=1                # Execution order (run first)
MIDDLEWARE_ERROR_INCLUDE_TRACEBACK=false # Include traceback in responses
MIDDLEWARE_ERROR_LOG_ERRORS=true        # Log errors to system logs
```

## Performance Tuning

### Retry Configuration

```bash
# Exponential Backoff Retry Settings
MAX_RETRIES=3                   # Maximum retry attempts
RETRY_BASE_DELAY=1.0            # Initial delay between retries (seconds)
RETRY_MAX_DELAY=60.0            # Maximum delay between retries (seconds)
RETRY_EXPONENTIAL_BASE=2.0      # Base for exponential backoff calculation
RETRY_JITTER=true               # Add randomization to retry delays
RETRY_TIMEOUT_FACTOR=1.5        # Multiply timeout by this factor on retry
```

### Circuit Breaker

```bash
# Circuit Breaker Configuration
CIRCUIT_BREAKER_ENABLED=true    # Enable circuit breaker pattern
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5    # Failures before opening circuit
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60    # Seconds before attempting recovery
CIRCUIT_BREAKER_EXPECTED_EXCEPTION_RATE=0.5  # Expected failure rate
```

### Connection Pooling

```bash
# HTTP Connection Pooling
HTTP_POOL_CONNECTIONS=10        # Number of connection pools
HTTP_POOL_MAXSIZE=10           # Maximum connections per pool
HTTP_MAX_RETRIES=3             # Maximum HTTP retries
HTTP_POOL_BLOCK=false          # Block when pool is full
```

## Production Settings

### High-Performance Configuration

```bash
# Production Optimizations
LOG_LEVEL=WARNING               # Reduce logging overhead
CACHE_REDIS_ENABLED=true        # Use Redis for better caching
REDIS_MAX_CONNECTIONS=20        # Increase Redis connections
MAX_CONCURRENT_REQUESTS=20      # Increase concurrency
MIDDLEWARE_LOGGING_INCLUDE_BODY=false  # Disable body logging
```

### Monitoring and Metrics

```bash
# Monitoring Configuration
METRICS_ENABLED=true            # Enable metrics collection
METRICS_ENDPOINT=/metrics       # Metrics endpoint path
HEALTH_CHECK_ENABLED=true       # Enable health check endpoint
HEALTH_CHECK_ENDPOINT=/health   # Health check endpoint path
STATS_COLLECTION_ENABLED=true   # Enable usage statistics
```

### Security Hardening

```bash
# Security Settings for Production
CORS_ORIGINS=https://yourdomain.com  # Restrict CORS origins
MIDDLEWARE_AUTH_ENABLED=true    # Enable authentication
RATE_LIMIT_REQUESTS=50          # Lower rate limits
MIDDLEWARE_ERROR_INCLUDE_TRACEBACK=false  # Hide error details
LOG_LEVEL=WARNING               # Reduce information disclosure
```

## Configuration Examples

### Development Environment

```bash
# .env for development
HOST=127.0.0.1
PORT=8000
LOG_LEVEL=DEBUG
TRANSPORT=http

# Enable all providers for testing
LINKUP_ENABLED=true
EXA_ENABLED=true
PERPLEXITY_ENABLED=true
TAVILY_ENABLED=true
FIRECRAWL_ENABLED=true

# Relaxed settings for development
DEFAULT_BUDGET=1.0
CACHE_TTL=60
MIDDLEWARE_LOGGING_INCLUDE_BODY=true
```

### Production Environment

```bash
# .env for production
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
TRANSPORT=http

# Redis caching for performance
REDIS_CACHE_ENABLED=true
REDIS_URL=redis://redis:6379
CACHE_REDIS_TTL=7200

# Security and performance
MIDDLEWARE_AUTH_ENABLED=true
RATE_LIMIT_ENABLED=true
MAX_CONCURRENT_REQUESTS=30
CIRCUIT_BREAKER_ENABLED=true

# Monitoring
METRICS_ENABLED=true
HEALTH_CHECK_ENABLED=true
```

### Claude Desktop Integration

```bash
# .env for Claude Desktop (STDIO transport)
TRANSPORT=stdio
LOG_LEVEL=WARNING

# Minimal provider set for desktop use
LINKUP_ENABLED=true
EXA_ENABLED=true
PERPLEXITY_ENABLED=false
TAVILY_ENABLED=false
FIRECRAWL_ENABLED=false

# Conservative settings
DEFAULT_BUDGET=0.05
LINKUP_TIMEOUT=5000
EXA_TIMEOUT=5000
```

## Validation and Testing

### Configuration Validation

Test your configuration:

```bash
# Validate configuration
python -m mcp_search_hub.config.validate

# Test provider connections
python -m mcp_search_hub.providers.test_connections

# Check server startup
python -m mcp_search_hub.main --validate-config
```

### Environment-Specific Testing

```bash
# Test development config
python -m mcp_search_hub.main --env development

# Test production config
python -m mcp_search_hub.main --env production --dry-run

# Test with specific providers only
LINKUP_ENABLED=true EXA_ENABLED=false python -m mcp_search_hub.main
```

## Troubleshooting

### Common Configuration Issues

**❌ "Provider not enabled" errors**
```bash
# Check provider enablement
echo $LINKUP_ENABLED
# Ensure API key is set
echo $LINKUP_API_KEY
```

**❌ "Redis connection failed" errors**
```bash
# Test Redis connectivity
redis-cli ping
# Disable Redis if not available
REDIS_CACHE_ENABLED=false
```

**❌ High memory usage**
```bash
# Reduce cache size
CACHE_MAX_SIZE=500
CACHE_TTL=180
# Enable Redis for external caching
REDIS_CACHE_ENABLED=true
```

**❌ Slow response times**
```bash
# Increase timeouts
LINKUP_TIMEOUT=15000
EXA_TIMEOUT=20000
# Increase concurrency
MAX_CONCURRENT_REQUESTS=20
```

### Configuration Debugging

Enable debug logging to troubleshoot configuration issues:

```bash
LOG_LEVEL=DEBUG python -m mcp_search_hub.main
```

Check the startup logs for configuration validation messages and any warnings about missing or invalid settings.

### Best Practices

1. **Start Minimal**: Begin with basic API keys and default settings
2. **Monitor Performance**: Use metrics to identify bottlenecks
3. **Gradual Optimization**: Adjust one setting at a time
4. **Environment Separation**: Use different configs for dev/staging/prod
5. **Security First**: Never commit API keys to version control
6. **Document Changes**: Keep track of configuration changes and their effects

---

For more configuration examples and advanced setups, see the [examples directory](examples/) in the repository.