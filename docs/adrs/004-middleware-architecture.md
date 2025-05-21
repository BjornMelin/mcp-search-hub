# ADR-004: Middleware Architecture

## Status

Accepted

## Context

MCP Search Hub needed a comprehensive middleware system to handle cross-cutting concerns like authentication, rate limiting, logging, error handling, and retry logic. These concerns were initially scattered throughout the codebase, leading to code duplication and inconsistent behavior.

Key requirements:
- Centralized handling of cross-cutting concerns
- Configurable middleware pipeline with ordering
- Support for both MCP and HTTP transports
- Consistent error handling and logging
- Rate limiting and quota management
- Retry logic for transient failures

## Decision

We decided to implement a **Centralized Middleware Architecture** that processes all requests through a configurable pipeline:

1. **MiddlewareManager**: Central orchestrator for middleware processing
2. **Base Middleware Classes**: Common interfaces and patterns
3. **Ordered Pipeline**: Configurable middleware execution order
4. **Transport Agnostic**: Works with both MCP and HTTP requests
5. **Configuration-Driven**: All middleware configurable via settings

### Middleware Components

- `ErrorHandlerMiddleware`: Centralized error handling and response formatting
- `LoggingMiddleware`: Request/response logging with configurable detail levels
- `AuthMiddleware`: API key validation and authentication
- `RateLimitMiddleware`: Request rate limiting and quota enforcement
- `RetryMiddleware`: Automatic retry logic for transient failures

## Consequences

### Positive

- **Centralized Logic**: All cross-cutting concerns in one place
- **Consistent Behavior**: Uniform handling across all request types
- **Configurable Pipeline**: Easy to enable/disable and reorder middleware
- **Reduced Duplication**: Eliminated scattered authentication and logging code
- **Better Debugging**: Centralized logging and error handling
- **Flexible Configuration**: Environment-based middleware configuration

### Negative

- **Increased Complexity**: More abstract architecture requires understanding
- **Performance Overhead**: Each request passes through multiple middleware layers
- **Debugging Complexity**: Issues may span multiple middleware components

### Trade-offs

- **Performance vs. Maintainability**: Slight overhead for much better organization
- **Flexibility vs. Simplicity**: More complex but highly configurable
- **Consistency vs. Optimization**: Uniform handling may not be optimal for all cases

## Implementation Details

```python
# Middleware pipeline configuration
middleware_manager = MiddlewareManager()

# Add middleware in execution order
middleware_manager.add_middleware(
    ErrorHandlerMiddleware,
    enabled=True,
    order=1,  # Runs first (lowest order)
    include_traceback=False,
    redact_sensitive_data=True,
)

middleware_manager.add_middleware(
    LoggingMiddleware,
    enabled=True,
    order=2,
    log_level="INFO",
    include_headers=True,
    sensitive_headers=["authorization", "x-api-key"],
)

middleware_manager.add_middleware(
    AuthMiddleware,
    enabled=True,
    order=3,
    require_api_key=False,  # Optional for MCP usage
)
```

### Middleware Processing Flow

```python
async def process_request(self, request, call_next):
    """Process request through middleware pipeline."""
    # Pre-processing (ordered by priority)
    for middleware in sorted(self.middleware, key=lambda m: m.order):
        request = await middleware.pre_process(request)
    
    # Execute main handler
    response = await call_next(request)
    
    # Post-processing (reverse order)
    for middleware in sorted(self.middleware, key=lambda m: -m.order):
        response = await middleware.post_process(request, response)
    
    return response
```

### Configuration Schema

```python
# Middleware configuration in settings
middleware:
  error_handler:
    enabled: true
    order: 1
    include_traceback: false
    redact_sensitive_data: true
  
  logging:
    enabled: true
    order: 2
    log_level: "INFO"
    include_headers: true
    include_body: false
    sensitive_headers: ["authorization", "x-api-key"]
  
  auth:
    enabled: true
    order: 3
    require_api_key: false
    allowed_origins: ["*"]
  
  rate_limit:
    enabled: true
    order: 4
    requests_per_minute: 60
    burst_size: 10
```

## Error Handling Strategy

The error handling middleware provides:
- **Consistent Error Responses**: Uniform error format across all endpoints
- **Sensitive Data Redaction**: Automatic removal of API keys and secrets
- **Contextual Information**: Request ID tracking for debugging
- **Graceful Degradation**: Fallback responses for middleware failures

```python
# Standard error response format
{
    "error": {
        "type": "ValidationError",
        "message": "Invalid query parameter",
        "request_id": "req_123456789",
        "timestamp": "2025-01-01T12:00:00Z"
    }
}
```

## Logging Strategy

The logging middleware provides:
- **Structured Logging**: JSON format for better parsing
- **Request Correlation**: Unique request IDs for tracing
- **Performance Metrics**: Request duration and status tracking
- **Configurable Detail**: Different log levels for different environments

```python
# Example log entry
{
    "timestamp": "2025-01-01T12:00:00Z",
    "level": "INFO",
    "request_id": "req_123456789",
    "method": "POST",
    "path": "/search",
    "status_code": 200,
    "duration_ms": 150,
    "user_agent": "mcp-client/1.0"
}
```

## Rate Limiting Implementation

- **Per-Client Limits**: Based on API key or IP address
- **Multiple Time Windows**: Per-minute, per-hour, per-day limits
- **Burst Handling**: Allow temporary bursts within limits
- **Graceful Responses**: Clear error messages when limits exceeded

## Alternatives Considered

1. **No Middleware System**: Handle concerns in individual handlers
   - Rejected: Code duplication and inconsistent behavior
   
2. **Framework Middleware**: Use only Starlette/FastAPI middleware
   - Rejected: Doesn't work with MCP transport
   
3. **Decorator Pattern**: Use Python decorators for cross-cutting concerns
   - Rejected: Less flexible than pipeline approach

## Migration Impact

The middleware architecture required:
- Moving authentication logic from individual handlers
- Centralizing error handling patterns
- Updating logging to use structured format
- Configuring middleware pipeline in settings
- Testing both MCP and HTTP transports

## Performance Considerations

- **Minimal Overhead**: Each middleware adds ~1-2ms per request
- **Short-Circuit Logic**: Failed authentication stops pipeline early
- **Async Processing**: All middleware operations are asynchronous
- **Memory Efficient**: Minimal state maintained between requests

## Related Decisions

- [ADR-001: Provider Integration Architecture](./001-provider-integration-architecture.md)
- [ADR-002: Routing System Design](./002-routing-system-design.md)
- [ADR-003: Caching Implementation](./003-caching-implementation.md)