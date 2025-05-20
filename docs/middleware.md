# Middleware Architecture

This document describes the middleware architecture implemented in MCP Search Hub.

## Overview

The middleware system provides a flexible and extensible way to process both HTTP requests and tool invocations before they reach their handlers, and to process the resulting responses before they are returned. This allows for centralized implementation of cross-cutting concerns such as authentication, rate limiting, logging, and potentially other features in the future.

The architecture follows a pipeline pattern where requests flow through a series of middleware components. Each middleware can examine and modify the request before passing it to the next component, and examine and modify the response on the way back.

## Key Components

### BaseMiddleware

`BaseMiddleware` is the abstract base class for all middleware components. It defines the core interface and provides common functionality:

```python
class BaseMiddleware(abc.ABC):
    """Base class for middleware components."""
    
    def __init__(self, **options):
        """Initialize the middleware."""
        self.options = options
        self.enabled = options.get("enabled", True)
        self.order = options.get("order", 100)
        self.logger = get_logger(self.__class__.__module__)
        self.name = self.__class__.__name__
        self._initialize(**options)
    
    def _initialize(self, **options):
        """Additional initialization that subclasses can override."""
        pass
    
    @abc.abstractmethod
    async def process_request(self, request: Any, context: Optional[Context] = None) -> Any:
        """Process the incoming request."""
        return request
    
    @abc.abstractmethod
    async def process_response(self, response: Any, request: Any, context: Optional[Context] = None) -> Any:
        """Process the outgoing response."""
        return response
```

The middleware system supports both HTTP requests/responses and tool invocations, with a unified interface for both types. The `process_request` and `process_response` methods handle the actual middleware logic and can be customized by subclasses.

### MiddlewareManager

`MiddlewareManager` is responsible for coordinating middleware execution. It:

1. Maintains a sorted list of middleware components
2. Orchestrates the execution of middleware chains
3. Provides methods for both HTTP and tool middleware processing
4. Creates middleware functions for HTTP and tool contexts

```python
class MiddlewareManager:
    """Manages the middleware pipeline for MCP Search Hub."""
    
    def __init__(self):
        """Initialize the middleware manager."""
        self.middlewares: List[BaseMiddleware] = []
        self.http_middlewares: List[BaseHTTPMiddleware] = []
        
    def add_middleware(self, middleware_class: type[BaseMiddleware], **options):
        """Add a middleware to the middleware stack."""
        # ... implementation ...
        
    async def process_http_request(self, request: Request, call_next) -> Response:
        """Process an HTTP request through the middleware stack."""
        # ... implementation ...
    
    async def process_tool_request(self, params: dict, context: Context, handler) -> Any:
        """Process a tool request through the middleware stack."""
        # ... implementation ...
```

The manager ensures middleware components are executed in the correct order (based on their `order` value), and handles the creation of middleware pipelines.

## Included Middleware Components

### 1. AuthMiddleware

The `AuthMiddleware` handles API key authentication for HTTP requests:

- Verifies API keys from `X-API-Key` or `Authorization` headers
- Allows configurable paths to skip authentication (e.g., `/health`, `/metrics`)
- Returns standardized error responses for authentication failures

### 2. RateLimitMiddleware

The `RateLimitMiddleware` implements rate limiting for HTTP requests:

- Uses a sliding window algorithm for rate limiting
- Supports both global rate limits and per-client rate limits
- Identifies clients by IP address, forwarded IP, or API key
- Adds rate limit headers to responses
- Returns standardized error responses when rate limits are exceeded

### 3. LoggingMiddleware

The `LoggingMiddleware` provides centralized request/response logging:

- Logs detailed information about incoming requests and outgoing responses
- Supports HTTP requests and tool invocations with a unified interface
- Generates trace IDs for request tracking
- Redacts sensitive information from logs (e.g., API keys)
- Configurable log level and content inclusion

### 4. RetryMiddleware

The `RetryMiddleware` implements exponential backoff retry logic for transient failures:

- Automatically retries failed requests with configurable exponential backoff
- Handles HTTP requests and tool invocations with a unified interface
- Intelligently identifies retryable errors (timeouts, connection issues, rate limits)
- Configurable max retries, delays, and jitter settings
- Skips specified paths to avoid retrying non-idempotent endpoints
- Replaces the previous decorator-based approach with a consistent middleware pattern

## Integration with Server

The middleware system is integrated with the SearchServer class to process both HTTP requests and tool invocations.

### HTTP Request Integration

For HTTP requests, middleware is registered as a Starlette middleware component:

```python
class MiddlewareHTTPWrapper(BaseHTTPMiddleware):
    """HTTP middleware wrapper for the middleware manager."""
    
    def __init__(self, app, middleware_manager):
        super().__init__(app)
        self.middleware_manager = middleware_manager
        
    async def dispatch(self, request, call_next):
        """Process HTTP request through middleware manager."""
        # ... implementation ...
```

This wrapper delegates to the middleware manager for processing HTTP requests through the middleware pipeline.

### Tool Invocation Integration

For tool invocations, middleware is applied by wrapping tool handler functions:

```python
async def search_with_middleware(query: str, ctx: Context, **kwargs) -> SearchResponse:
    """Execute a search query with middleware processing."""
    # Prepare parameters for middleware
    params = {
        "query": query,
        **kwargs,
        "tool_name": "search",  # Include tool name for middleware
    }
    
    # Create handler function
    async def handler(**p):
        # ... implementation ...
        
    # Process through middleware
    return await self.middleware_manager.process_tool_request(params, ctx, handler)
```

The middleware system is initialized during server startup:

```python
def _setup_middleware(self):
    """Set up and configure middleware components."""
    middleware_config = self.settings.middleware
    
    # Add logging middleware
    if middleware_config.logging.enabled:
        self.middleware_manager.add_middleware(LoggingMiddleware, ...)
    
    # Add authentication middleware
    if middleware_config.auth.enabled:
        self.middleware_manager.add_middleware(AuthMiddleware, ...)
    
    # Add rate limiting middleware
    if middleware_config.rate_limit.enabled:
        self.middleware_manager.add_middleware(RateLimitMiddleware, ...)
```

## Configuration

Middleware is configured using environment variables and Pydantic models:

```python
class LoggingMiddlewareConfig(BaseModel):
    """Configuration for logging middleware."""
    enabled: bool = True
    order: int = 5
    log_level: str = "INFO"
    include_headers: bool = True
    include_body: bool = False
    sensitive_headers: List[str] = ["authorization", "x-api-key", "cookie", "set-cookie"]
    max_body_size: int = 1024

class AuthMiddlewareConfig(BaseModel):
    """Configuration for authentication middleware."""
    enabled: bool = True
    order: int = 10
    api_keys: List[SecretStr] = []
    skip_auth_paths: List[str] = ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]

class RateLimitMiddlewareConfig(BaseModel):
    """Configuration for rate limiting middleware."""
    enabled: bool = True
    order: int = 20
    limit: int = 100
    window: int = 60
    global_limit: int = 1000
    global_window: int = 60
    skip_paths: List[str] = ["/health", "/metrics"]

class MiddlewareConfig(BaseModel):
    """Configuration for all middleware components."""
    logging: LoggingMiddlewareConfig = LoggingMiddlewareConfig()
    auth: AuthMiddlewareConfig = AuthMiddlewareConfig()
    rate_limit: RateLimitMiddlewareConfig = RateLimitMiddlewareConfig()
```

## Error Handling

The middleware system includes error handling to ensure that errors in middleware components don't crash the server:

1. In the middleware pipeline, errors are caught and propagated
2. For HTTP requests, errors are converted to appropriate HTTP responses
3. For tool invocations, errors are caught and can be handled by the caller

## Middleware Ordering

Middleware components are executed in order of their `order` value (lower values run first). The default ordering is:

1. LoggingMiddleware (order=5): Runs first to log all requests
2. AuthMiddleware (order=10): Runs early to reject unauthorized requests
3. RateLimitMiddleware (order=20): Runs after auth to apply rate limits

This ordering ensures that:
- All requests are logged, even unauthorized ones
- Authentication is verified before applying rate limits
- Rejected requests don't count against rate limits

## Extending the Middleware System

To create a new middleware component:

1. Subclass `BaseMiddleware`
2. Implement `process_request` and `process_response` methods
3. Add configuration to `MiddlewareConfig` if needed
4. Register the middleware in `_setup_middleware`

Example of a simple middleware implementation:

```python
class TimingMiddleware(BaseMiddleware):
    """Middleware to track request timing."""
    
    def _initialize(self, **options):
        """Initialize timing middleware."""
        self.order = options.get("order", 15)
        
    async def process_request(self, request, context=None):
        """Start timing the request."""
        if isinstance(request, dict):
            request = request.copy()
            request["start_time"] = time.perf_counter()
        return request
        
    async def process_response(self, response, request, context=None):
        """Add timing information to response."""
        if isinstance(request, dict) and "start_time" in request:
            start_time = request["start_time"]
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            if isinstance(response, dict):
                response = response.copy()
                response["request_duration_ms"] = round(duration_ms, 2)
                
        return response
```