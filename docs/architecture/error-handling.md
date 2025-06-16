# Unified Error Handling in MCP Search Hub

This document describes the unified error handling approach implemented in MCP Search Hub.

## Overview

MCP Search Hub implements a comprehensive and consistent error handling system that ensures:

1. All errors are properly classified and categorized
2. Error messages are informative and user-friendly
3. Errors are propagated correctly through middleware and handlers
4. HTTP error responses follow a consistent format
5. Error details are appropriately logged
6. Transient errors can be retried automatically
7. Sensitive information is properly redacted from error messages and logs

This unified approach replaces the previously inconsistent error handling methods that were used in different parts of the application.

## Key Components

### 1. Error Hierarchy

A comprehensive hierarchy of error classes built on the base `SearchError` class. This hierarchy allows for specific error types with appropriate status codes and context:

- `SearchError` - Base error class
  - `ProviderError` - Provider-related errors
    - `ProviderNotFoundError` - Provider doesn't exist
    - `ProviderNotEnabledError` - Provider exists but is disabled
    - `ProviderInitializationError` - Provider failed to initialize
    - `ProviderTimeoutError` - Provider operation timed out
    - `ProviderRateLimitError` - Provider rate limit exceeded
    - `ProviderAuthenticationError` - Provider authentication failed
    - `ProviderQuotaExceededError` - Provider quota exceeded
    - `ProviderServiceError` - Generic provider service error
  - `QueryError` - Query-related errors
    - `QueryValidationError` - Query failed validation
    - `QueryTooComplexError` - Query is too complex to process
    - `QueryBudgetExceededError` - Query would exceed budget
  - `RouterError` - Routing-related errors
    - `NoProvidersAvailableError` - No providers available for query
    - `CircuitBreakerOpenError` - Circuit breaker is open for provider
    - `RoutingStrategyError` - Routing strategy failed
  - `ConfigurationError` - Configuration-related errors
    - `MissingConfigurationError` - Required configuration is missing
    - `InvalidConfigurationError` - Configuration has invalid value
  - `AuthenticationError` - Authentication failed
  - `AuthorizationError` - Authorization failed
  - `NetworkError` - Network-related errors
    - `NetworkConnectionError` - Connection failed
    - `NetworkTimeoutError` - Network operation timed out

### 2. Error Handler Middleware

The `ErrorHandlerMiddleware` component provides centralized error handling for all middleware components and ensures consistent formatting of error responses:

- Catches exceptions from all middleware components
- Converts exceptions to standardized error responses
- Preserves error context and details
- Handles special cases like rate limit headers
- Ensures appropriate HTTP status codes
- Applies consistent error response structure

### 3. Standardized Error Response Format

All error responses follow a consistent format:

```json
{
  "error_type": "ErrorClassName",
  "message": "Human-readable error message",
  "status_code": 400,
  "provider": "provider_name",  // When applicable
  "details": {
    // Additional context-specific error details
  }
}
```

This structure ensures that clients can easily understand and handle errors, and that error responses include sufficient context for troubleshooting.

## Middleware Error Handling Flow

1. **Error Detection**: An error occurs in a middleware component or handler.
2. **Error Classification**: The error is wrapped in an appropriate `SearchError` subclass if it isn't already.
3. **Error Logging**: The error is logged with appropriate context and severity.
4. **Error Propagation**: The error is propagated through the middleware chain.
5. **Error Handling**: The `ErrorHandlerMiddleware` catches the error and formats it into a standardized response.
6. **Response Generation**: The formatted error is returned to the client.

## Best Practices for Error Handling

When working with errors in the codebase, follow these guidelines:

### Raising Errors

1. Use the most specific error class available for the situation.
2. Include clear, actionable error messages.
3. Add relevant context in the `details` dictionary.
4. Set appropriate HTTP status codes.
5. Include provider information when applicable.

Example:

```python
if not auth_valid:
    raise AuthenticationError(
        message="Invalid API key format",
        details={"reason": "malformed_key"}
    )
```

### Catching and Converting Errors

1. Catch specific exception types when possible.
2. Convert external exceptions to appropriate `SearchError` subclasses.
3. Preserve the original error using the `original_error` parameter.
4. Add context about the operation that failed.

Example:

```python
try:
    response = await provider.search(query)
except httpx.TimeoutError as e:
    raise ProviderTimeoutError(
        provider=provider.name,
        operation="search",
        timeout=provider.timeout,
        original_error=e,
    )
except Exception as e:
    raise ProviderServiceError(
        provider=provider.name,
        message=f"Search failed: {str(e)}",
        original_error=e,
    )
```

### Error Responses in HTTP Handlers

1. Use the `http_error_response` utility to format error responses consistently.
2. Let the middleware handle error conversion automatically when possible.
3. Add appropriate headers for special error types (e.g., rate limiting).

Example:

```python
@router.get("/search")
async def search_endpoint(query: str, request: Request):
    try:
        response = await search_service.search(query)
        return response
    except SearchError as e:
        # The ErrorHandlerMiddleware will format this properly
        raise e
    except Exception as e:
        # Convert generic errors to SearchError
        raise SearchError(
            message=f"Search failed: {str(e)}",
            status_code=500,
            original_error=e,
        )
```

## Configuration

The error handling system is configurable through the `ErrorHandlerMiddlewareConfig` class:

```python
class ErrorHandlerMiddlewareConfig(BaseModel):
    """Configuration for error handler middleware."""

    enabled: bool = True
    order: int = 0  # Should run first to catch all errors
    include_traceback: bool = False
    redact_sensitive_data: bool = True
```

## Implementation Details

### Integration with Retry Middleware

The `RetryMiddleware` integrates with the error handling system to automatically retry operations that fail with transient errors:

1. Identifies retryable errors by examining the error type and status code
2. Applies exponential backoff to retry intervals
3. Preserves original error context for logging and debugging
4. Ensures consistent error propagation

### Sensitive Data Handling

The error handling system carefully redacts sensitive information:

1. Automatically redacts API keys, passwords, and authentication tokens
2. Avoids logging sensitive request/response data in error contexts
3. Filters sensitive fields from error details
4. Ensures consistent redaction across logging and error responses