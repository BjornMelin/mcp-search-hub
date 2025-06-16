# Middleware Architecture

MCP Search Hub implements a flexible middleware system for handling cross-cutting concerns like authentication, rate limiting, logging, and error handling in a centralized, composable way.

## Overview

The middleware system follows a pipeline pattern where requests flow through a series of middleware components. Each middleware can examine and modify the request before passing it to the next component, and process the response on the way back.

```mermaid
graph LR
    Request[Incoming Request] --> Auth[Auth Middleware]
    Auth --> RateLimit[Rate Limit Middleware]
    RateLimit --> Logging[Logging Middleware]
    Logging --> Handler[Request Handler]
    Handler --> Logging2[Logging Middleware]
    Logging2 --> RateLimit2[Rate Limit Middleware]
    RateLimit2 --> Auth2[Auth Middleware]
    Auth2 --> Response[Outgoing Response]
```

## Architecture Components

### Base Middleware

All middleware components inherit from `BaseMiddleware`:

```python
class BaseMiddleware(abc.ABC):
    """Base class for all middleware components."""
    
    def __init__(self, **options):
        self.enabled = options.get("enabled", True)
        self.order = options.get("order", 100)
        self.logger = get_logger(self.__class__.__module__)
        self.name = self.__class__.__name__
    
    @abc.abstractmethod
    async def process_request(self, request: Any, context: Optional[Context] = None) -> Any:
        """Process incoming request."""
        return request
    
    @abc.abstractmethod
    async def process_response(self, response: Any, request: Any, context: Optional[Context] = None) -> Any:
        """Process outgoing response."""
        return response
```

### Middleware Manager

The `MiddlewareManager` coordinates middleware execution:

```python
class MiddlewareManager:
    """Manages middleware pipeline execution."""
    
    def __init__(self):
        self.middlewares: List[BaseMiddleware] = []
    
    def add_middleware(self, middleware: BaseMiddleware):
        """Add middleware to the pipeline."""
        self.middlewares.append(middleware)
        # Sort by order for consistent execution
        self.middlewares.sort(key=lambda m: m.order)
    
    async def process_request(self, request: Any, context: Optional[Context] = None) -> Any:
        """Process request through all middleware."""
        for middleware in self.middlewares:
            if middleware.enabled:
                request = await middleware.process_request(request, context)
        return request
    
    async def process_response(self, response: Any, request: Any, context: Optional[Context] = None) -> Any:
        """Process response through all middleware (reverse order)."""
        for middleware in reversed(self.middlewares):
            if middleware.enabled:
                response = await middleware.process_response(response, request, context)
        return response
```

## Built-in Middleware Components

### Authentication Middleware

Handles API key authentication for HTTP endpoints:

```python
class AuthMiddleware(BaseMiddleware):
    """Authentication middleware using API keys."""
    
    def _initialize(self, **options):
        self.api_key = options.get("api_key")
        self.header_name = options.get("header", "X-API-Key")
        self.skip_paths = options.get("skip_paths", ["/health", "/metrics"])
    
    async def process_request(self, request: Any, context: Optional[Context] = None) -> Any:
        if self._should_skip_auth(request):
            return request
            
        api_key = self._extract_api_key(request)
        if not api_key or api_key != self.api_key:
            raise AuthenticationError("Invalid or missing API key")
            
        return request
    
    async def process_response(self, response: Any, request: Any, context: Optional[Context] = None) -> Any:
        return response
```

### Rate Limiting Middleware

Implements token bucket rate limiting:

```python
class RateLimitMiddleware(BaseMiddleware):
    """Rate limiting middleware with token bucket algorithm."""
    
    def _initialize(self, **options):
        self.limit = options.get("limit", 100)  # requests per window
        self.window = options.get("window", 60)  # window in seconds
        self.global_limit = options.get("global_limit", 1000)
        self.buckets = {}  # client_id -> bucket
        self.global_bucket = TokenBucket(self.global_limit, self.window)
    
    async def process_request(self, request: Any, context: Optional[Context] = None) -> Any:
        client_id = self._get_client_id(request)
        
        # Check global rate limit
        if not self.global_bucket.consume():
            raise RateLimitError("Global rate limit exceeded")
        
        # Check per-client rate limit
        bucket = self._get_or_create_bucket(client_id)
        if not bucket.consume():
            raise RateLimitError(f"Rate limit exceeded for client {client_id}")
            
        return request
    
    async def process_response(self, response: Any, request: Any, context: Optional[Context] = None) -> Any:
        # Add rate limit headers
        client_id = self._get_client_id(request)
        bucket = self.buckets.get(client_id)
        if bucket:
            response.headers["X-RateLimit-Limit"] = str(self.limit)
            response.headers["X-RateLimit-Remaining"] = str(bucket.tokens)
            response.headers["X-RateLimit-Reset"] = str(bucket.reset_time)
        return response
```

### Logging Middleware

Provides structured request/response logging:

```python
class LoggingMiddleware(BaseMiddleware):
    """Structured logging middleware."""
    
    def _initialize(self, **options):
        self.log_level = options.get("log_level", "INFO")
        self.include_headers = options.get("include_headers", True)
        self.include_body = options.get("include_body", False)
        self.max_body_size = options.get("max_body_size", 1024)
    
    async def process_request(self, request: Any, context: Optional[Context] = None) -> Any:
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        # Store timing info for response logging
        if context:
            context.start_time = start_time
            context.request_id = request_id
        
        log_data = {
            "event": "request_started",
            "request_id": request_id,
            "method": getattr(request, "method", "TOOL"),
            "path": getattr(request, "url", {}).get("path", ""),
            "user_agent": self._get_header(request, "user-agent")
        }
        
        if self.include_headers:
            log_data["headers"] = dict(getattr(request, "headers", {}))
        
        if self.include_body and hasattr(request, "body"):
            body = request.body[:self.max_body_size] if request.body else ""
            log_data["body"] = body
        
        self.logger.info("Request received", extra=log_data)
        return request
    
    async def process_response(self, response: Any, request: Any, context: Optional[Context] = None) -> Any:
        end_time = time.time()
        duration_ms = (end_time - context.start_time) * 1000 if context else 0
        
        log_data = {
            "event": "request_completed",
            "request_id": getattr(context, "request_id", "unknown"),
            "status_code": getattr(response, "status_code", 200),
            "duration_ms": round(duration_ms, 2)
        }
        
        if hasattr(response, "headers"):
            log_data["response_headers"] = dict(response.headers)
        
        self.logger.info("Request completed", extra=log_data)
        return response
```

### Error Handling Middleware

Provides consistent error handling and formatting:

```python
class ErrorHandlerMiddleware(BaseMiddleware):
    """Centralized error handling middleware."""
    
    def _initialize(self, **options):
        self.include_traceback = options.get("include_traceback", False)
        self.log_errors = options.get("log_errors", True)
    
    async def process_request(self, request: Any, context: Optional[Context] = None) -> Any:
        return request
    
    async def process_response(self, response: Any, request: Any, context: Optional[Context] = None) -> Any:
        # Error handling happens in the middleware manager's exception handling
        return response
    
    def handle_error(self, error: Exception, request: Any, context: Optional[Context] = None) -> Any:
        """Handle errors and format consistent error responses."""
        if self.log_errors:
            self.logger.error(f"Request failed: {error}", exc_info=True)
        
        if isinstance(error, SearchError):
            return self._format_search_error(error)
        elif isinstance(error, AuthenticationError):
            return self._format_auth_error(error)
        elif isinstance(error, RateLimitError):
            return self._format_rate_limit_error(error)
        else:
            return self._format_generic_error(error)
```

## Configuration

Middleware is configured through environment variables with a consistent pattern:

```bash
# Authentication Middleware
MIDDLEWARE_AUTH_ENABLED=true            # Enable/disable
MIDDLEWARE_AUTH_ORDER=10                # Execution order
MIDDLEWARE_AUTH_API_KEY=your_api_key    # API key for authentication
MIDDLEWARE_AUTH_HEADER=X-API-Key        # Header name for API key

# Rate Limiting Middleware
MIDDLEWARE_RATE_LIMIT_ENABLED=true      # Enable/disable
MIDDLEWARE_RATE_LIMIT_ORDER=20          # Execution order
MIDDLEWARE_RATE_LIMIT_LIMIT=100         # Requests per window per client
MIDDLEWARE_RATE_LIMIT_WINDOW=60         # Window in seconds
MIDDLEWARE_RATE_LIMIT_GLOBAL_LIMIT=1000 # Global requests per window

# Logging Middleware
MIDDLEWARE_LOGGING_ENABLED=true         # Enable/disable
MIDDLEWARE_LOGGING_ORDER=5              # Execution order (early)
MIDDLEWARE_LOGGING_LOG_LEVEL=INFO       # Log level
MIDDLEWARE_LOGGING_INCLUDE_HEADERS=true # Include headers in logs
MIDDLEWARE_LOGGING_INCLUDE_BODY=false   # Include request/response bodies
MIDDLEWARE_LOGGING_MAX_BODY_SIZE=1024   # Maximum body size to log

# Error Handling Middleware
MIDDLEWARE_ERROR_ENABLED=true           # Enable/disable
MIDDLEWARE_ERROR_ORDER=1                # Execution order (first)
MIDDLEWARE_ERROR_INCLUDE_TRACEBACK=false # Include traceback in responses
MIDDLEWARE_ERROR_LOG_ERRORS=true        # Log errors to system logs
```

## Middleware Registration

Middleware is automatically registered during server startup:

```python
class SearchServer:
    def __init__(self):
        self.middleware_manager = MiddlewareManager()
        self._register_middleware()
    
    def _register_middleware(self):
        """Register middleware based on configuration."""
        # Error handling (first)
        if self.settings.middleware.error.enabled:
            self.middleware_manager.add_middleware(
                ErrorHandlerMiddleware(**self.settings.middleware.error.dict())
            )
        
        # Logging (early)
        if self.settings.middleware.logging.enabled:
            self.middleware_manager.add_middleware(
                LoggingMiddleware(**self.settings.middleware.logging.dict())
            )
        
        # Authentication
        if self.settings.middleware.auth.enabled:
            self.middleware_manager.add_middleware(
                AuthMiddleware(**self.settings.middleware.auth.dict())
            )
        
        # Rate limiting
        if self.settings.middleware.rate_limit.enabled:
            self.middleware_manager.add_middleware(
                RateLimitMiddleware(**self.settings.middleware.rate_limit.dict())
            )
```

## Execution Flow

### Request Processing

1. **Error Handler**: Wraps entire pipeline in try/catch
2. **Logging**: Logs request start and captures timing
3. **Authentication**: Validates API keys (if enabled)
4. **Rate Limiting**: Checks request quotas
5. **Handler**: Processes the actual request
6. **Rate Limiting**: Updates quotas and adds headers
7. **Authentication**: No response processing needed
8. **Logging**: Logs request completion with timing
9. **Error Handler**: Formats any errors that occurred

### Tool Invocation Processing

For MCP tool invocations, the middleware system:

1. Converts tool calls to a standard request format
2. Processes through the middleware pipeline
3. Executes the tool handler
4. Processes the response back through middleware
5. Converts back to MCP response format

## Custom Middleware

To create custom middleware:

```python
class CustomMiddleware(BaseMiddleware):
    """Example custom middleware."""
    
    def _initialize(self, **options):
        self.custom_setting = options.get("custom_setting", "default")
    
    async def process_request(self, request: Any, context: Optional[Context] = None) -> Any:
        # Add custom request processing logic
        self.logger.info(f"Processing request with {self.custom_setting}")
        return request
    
    async def process_response(self, response: Any, request: Any, context: Optional[Context] = None) -> Any:
        # Add custom response processing logic
        self.logger.info("Processing response")
        return response

# Register custom middleware
middleware_manager.add_middleware(CustomMiddleware(
    enabled=True,
    order=50,
    custom_setting="my_value"
))
```

## Performance Considerations

### Middleware Ordering

- **Error Handler**: Order 1 (first to catch all errors)
- **Logging**: Order 5 (early for complete request tracking)
- **Authentication**: Order 10 (after logging, before business logic)
- **Rate Limiting**: Order 20 (after auth, before expensive operations)
- **Custom**: Order 50+ (after built-in middleware)

### Performance Impact

- **Logging**: Minimal overhead (~1-2ms per request)
- **Authentication**: Very low overhead (~0.5ms per request)
- **Rate Limiting**: Low overhead (~1ms per request)
- **Error Handling**: No overhead unless errors occur

### Best Practices

1. **Keep middleware lightweight**: Avoid heavy computations
2. **Use appropriate ordering**: Place expensive operations later
3. **Handle errors gracefully**: Don't let middleware failures break requests
4. **Log appropriately**: Balance debugging needs with performance
5. **Configure carefully**: Disable unnecessary middleware in production

## Monitoring and Debugging

### Middleware Metrics

```python
# Track middleware performance
middleware_metrics = {
    "middleware_execution_time": histogram("middleware_duration_seconds"),
    "middleware_errors": counter("middleware_errors_total"),
    "requests_processed": counter("middleware_requests_total")
}
```

### Debug Logging

```bash
# Enable debug logging for middleware
LOG_LEVEL=DEBUG
MIDDLEWARE_LOGGING_LOG_LEVEL=DEBUG

# Check middleware configuration
curl http://localhost:8000/health | jq .middleware_status
```

---

The middleware architecture provides a clean, extensible way to handle cross-cutting concerns while maintaining good performance and clear separation of responsibilities.