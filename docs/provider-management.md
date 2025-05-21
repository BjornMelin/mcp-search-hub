# Provider Management System

MCP Search Hub includes a comprehensive provider management system that helps control API usage, enforce rate limits, and track costs across all integrated search providers.

## Features

The provider management system consists of two main components:

1. **Rate Limiting**: Controls the frequency of API calls to prevent exceeding provider rate limits
2. **Budget Tracking**: Tracks and enforces budget constraints to control costs

### Rate Limiting

Each provider has configurable rate limits with multiple tiers:

- **Per-minute limits**: Controls short-term burst activity
- **Per-hour limits**: Provides medium-term throttling
- **Per-day limits**: Enforces daily quota restrictions
- **Concurrent request limits**: Prevents overloading providers with parallel requests

When a provider exceeds its rate limits, it enters a cooldown period during which new requests are rejected. This helps maintain good standing with each provider's API service.

### Budget Tracking

Budget tracking allows monitoring and controlling the cost of API usage:

- **Per-query budget**: Maximum cost allowed for a single query
- **Daily budget**: Maximum spending allowed per day
- **Monthly budget**: Maximum spending allowed per month

The system tracks actual costs based on query parameters and results, and can enforce spending limits to prevent exceeding budgets.

## Configuration

Both rate limiting and budget tracking are configurable through provider_config.py:

```python
# Example configuration for a provider
"exa": {
    "env_var": "EXA_API_KEY",
    "server_type": ServerType.NODE_JS,
    "package": "exa-mcp-server",
    "tool_name": "web_search_exa",
    "timeout": 15000,
    # Rate limits
    "rate_limits": RateLimitConfig(
        requests_per_minute=60,
        requests_per_hour=500,
        requests_per_day=5000,
        concurrent_requests=10,
    ),
    # Budget config
    "budget": BudgetConfig(
        default_query_budget=Decimal("0.02"),
        daily_budget=Decimal("10.00"),
        monthly_budget=Decimal("150.00"),
    ),
    # Base cost in USD per query
    "base_cost": Decimal("0.01"),
}
```

### Rate Limit Configuration

- `requests_per_minute`: Maximum number of requests allowed per minute
- `requests_per_hour`: Maximum number of requests allowed per hour
- `requests_per_day`: Maximum number of requests allowed per day
- `concurrent_requests`: Maximum number of concurrent requests allowed
- `cooldown_period`: Time in seconds to wait after hitting a rate limit

### Budget Configuration

- `default_query_budget`: Maximum cost allowed for a single query (in USD)
- `daily_budget`: Maximum spending allowed per day (in USD)
- `monthly_budget`: Maximum spending allowed per month (in USD)
- `enforce_budget`: Whether to enforce budget constraints

## Monitoring

The provider management system provides monitoring capabilities through several endpoints:

### Usage Statistics Endpoint

`GET /usage` returns detailed statistics about provider usage, including:

- Current rate limit status for each provider
- Budget usage and remaining budget
- Provider capabilities and cost tracking
- Rate-limited and budget-exceeded providers

Example response:

```json
{
  "exa": {
    "status": "ok",
    "rate_limited": false,
    "budget_exceeded": false,
    "rate_limits": {
      "minute_remaining": 58,
      "hour_remaining": 495,
      "day_remaining": 4995,
      "concurrent_remaining": 10
    },
    "budget": {
      "query_budget": "0.02",
      "daily_remaining": "9.75",
      "monthly_remaining": "149.75"
    },
    "cost_tracking": {
      "base_cost": 0.01,
      "estimated_daily_cost": 0.25,
      "estimated_monthly_cost": 0.25
    },
    "capabilities": {
      "name": "exa",
      "supports_raw_content": true,
      "supports_advanced_search": true,
      "max_results_per_query": 10,
      "features": [
        "search_filters",
        "date_range_filtering",
        "content_extraction",
        "semantic_search",
        "highlights",
        "research_paper_search",
        "company_research",
        "competitor_finder",
        "linkedin_search",
        "wikipedia_search",
        "github_search"
      ],
      "rate_limit_info": {
        "minute_requests": 2,
        "hour_requests": 5,
        "day_requests": 5,
        "concurrent_requests": 0
      },
      "budget_info": {
        "daily_cost": "0.25",
        "monthly_cost": "0.25",
        "daily_budget": "10.00",
        "monthly_budget": "150.00",
        "daily_percent_used": "2.5",
        "monthly_percent_used": "0.17"
      }
    }
  },
  // Additional providers...
}
```

### Health Endpoint

The enhanced `/health` endpoint now includes rate limiting and budget status:

- Providers that are rate limited will show `DEGRADED` health status
- Providers that have exceeded their budget will show `DEGRADED` health status
- Status messages include rate limiting and budget information

## Programmatic Access

The provider management system can be accessed programmatically through the following classes:

### Rate Limiting

```python
from mcp_search_hub.providers.rate_limiter import rate_limiter_manager

# Get rate limiter for a provider
limiter = rate_limiter_manager.get_limiter("provider_name")

# Check if provider is rate limited
is_limited = limiter.is_in_cooldown()

# Get usage statistics
usage = limiter.get_current_usage()

# Get remaining quota
remaining = limiter.get_remaining_quota()
```

### Budget Tracking

```python
from mcp_search_hub.providers.budget_tracker import budget_tracker_manager

# Get budget tracker for a provider
tracker = budget_tracker_manager.get_tracker("provider_name")

# Check if budget allows a specific cost
allowed = await tracker.check_budget(Decimal("0.05"))

# Record a cost
await tracker.record_cost(Decimal("0.05"))

# Get usage report
report = tracker.get_usage_report()

# Get remaining budget
remaining = tracker.get_remaining_budget()
```

### Usage Statistics

```python
from mcp_search_hub.utils.usage_stats import UsageStats

# Get all rate limits
rate_limits = UsageStats.get_all_rate_limits()

# Get all budgets
budgets = UsageStats.get_all_budgets()

# Get rate limited providers
limited = UsageStats.get_rate_limited_providers()

# Get budget exceeded providers
exceeded = UsageStats.get_budget_exceeded_providers()

# Get comprehensive status report
report = UsageStats.get_provider_status_report()
```

## Best Practices

1. **Set appropriate rate limits**: Adjust rate limits based on each provider's documented API limits
2. **Set realistic budgets**: Consider your usage patterns and provider pricing
3. **Monitor usage regularly**: Check the `/usage` endpoint to track rate limit and budget status
4. **Handle rate limiting gracefully**: Implement backoff strategies in client applications
5. **Adjust budgets monthly**: Review and adjust budgets based on actual usage patterns