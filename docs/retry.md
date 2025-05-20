# Exponential Backoff Retry Logic

This document describes the exponential backoff retry implementation in MCP Search Hub.

## Overview

The retry logic provides a robust mechanism for handling transient errors when making API calls to external services. It automatically retries failed operations using an exponential backoff strategy with configurable parameters.

## Key Features

- **Exponential Backoff**: Increases delay between retry attempts exponentially to avoid overwhelming services
- **Jitter**: Adds randomization to retry timings to prevent thundering herd problem
- **Smart Exception Classification**: Intelligently identifies which exceptions should trigger retries
- **Comprehensive Logging**: Provides detailed logging of retry attempts and outcomes
- **Configurable**: All retry parameters are configurable via environment variables
- **Provider Integration**: All search providers automatically use retry logic

## Usage

The retry functionality can be used in two ways:

### 1. Function Decorator

```python
from mcp_search_hub.utils.retry import with_exponential_backoff

@with_exponential_backoff()  # Uses default configuration
async def make_api_call():
    # API call that might fail transiently
    response = await httpx.get("https://api.example.com/data")
    response.raise_for_status()
    return response.json()
```

### 2. Function Wrapper

```python
from mcp_search_hub.utils.retry import retry_async

async def fetch_data(url):
    response = await httpx.get(url)
    response.raise_for_status()
    return response.json()

# Wrap the function call with retry logic
data = await retry_async(fetch_data, "https://api.example.com/data")
```

### 3. Provider Mixin

Provider classes use the `RetryMixin` class to add retry functionality:

```python
from mcp_search_hub.providers.retry_mixin import RetryMixin

class MyProvider(RetryMixin):
    async def search(self, query):
        """Execute a search query with retry logic."""
        return await self.with_retry(self._search_impl)(query)
        
    async def _search_impl(self, query):
        # Actual search implementation that might fail
```

## Configuration

Retry behavior is configured via settings in the environment:

| Parameter | Environment Variable | Default | Description |
|-----------|----------------------|---------|-------------|
| Max Retries | `RETRY_MAX_RETRIES` | 3 | Maximum number of retry attempts |
| Base Delay | `RETRY_BASE_DELAY` | 1.0 | Initial delay between retries in seconds |
| Max Delay | `RETRY_MAX_DELAY` | 60.0 | Maximum delay cap in seconds |
| Exponential Base | `RETRY_EXPONENTIAL_BASE` | 2.0 | Base for exponential calculation |
| Jitter | `RETRY_JITTER` | true | Whether to add randomization to delays |

## Retry Algorithm

The retry delay is calculated using the following formula:

```
delay = min(base_delay * (exponential_base ^ attempt), max_delay)
```

When jitter is enabled, a random adjustment of ±25% is applied to the calculated delay.

## Retryable Exceptions

The following exceptions trigger retries automatically:

### Network Errors
- `httpx.TimeoutException`: Connection or read timeouts
- `httpx.ConnectError`: Connection errors
- `httpx.RemoteProtocolError`: Protocol errors
- `ConnectionError`: Generic connection errors
- `TimeoutError`: Generic timeout errors
- `ProviderTimeoutError`: Custom provider timeouts

### HTTP Status Codes
- 408: Request Timeout
- 429: Too Many Requests (Rate Limiting)
- 500: Internal Server Error
- 502: Bad Gateway
- 503: Service Unavailable
- 504: Gateway Timeout

### Custom Errors
- `SearchError` instances containing "temporary" or "timeout" in their message

## Logging

The retry system logs detailed information about retry attempts:

- **Warning Level**: Each retry attempt logs:
  - Function name and attempt count
  - Timestamp
  - Exception details
  - Next retry delay
  - Request URL and method (if available)

- **Info Level**: Successful completion after retries logs:
  - Function name
  - Number of retries needed
  - Total time elapsed

- **Error Level**: Retry exhaustion logs:
  - Function name
  - Total time elapsed
  - Final exception details

- **Debug Level**: Non-retryable exceptions logs:
  - Function name
  - Exception details
  - Stack trace (when debug level is enabled)

## Provider Integration

All search providers in MCP Search Hub integrate with the retry system through the `RetryMixin` class. This ensures that API calls to all search services automatically benefit from retry logic.

Each provider can customize its retry configuration through settings, allowing for provider-specific retry behavior if needed.

## Testing

The retry implementation includes comprehensive test coverage:

- Unit tests for all retry functionality
- Integration tests with HTTP clients
- Tests for edge cases and error conditions
- Tests for all provider implementations

## Implementation Details

The retry functionality is implemented in:

- `utils/retry.py`: Core retry implementation
- `providers/retry_mixin.py`: Provider integration
- `models/config.py`: Configuration models

The implementation follows best practices for Python async code and exception handling.