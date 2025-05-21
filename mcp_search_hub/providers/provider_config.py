"""Configuration for provider implementations."""

from decimal import Decimal

from .base_mcp import ServerType
from .budget_tracker import BudgetConfig
from .rate_limiter import RateLimitConfig

# Provider configurations for all MCP providers
PROVIDER_CONFIGS = {
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
    },
    "firecrawl": {
        "env_var": "FIRECRAWL_API_KEY",
        "server_type": ServerType.NODE_JS,
        "package": "firecrawl-mcp",
        "tool_name": "firecrawl_search",
        "timeout": 30000,
        # Command-line args
        "args": ["firecrawl-mcp"],
        # Rate limits
        "rate_limits": RateLimitConfig(
            requests_per_minute=30,
            requests_per_hour=300,
            requests_per_day=3000,
            concurrent_requests=5,
        ),
        # Budget config
        "budget": BudgetConfig(
            default_query_budget=Decimal("0.05"),
            daily_budget=Decimal("15.00"),
            monthly_budget=Decimal("200.00"),
        ),
        # Base cost in USD per query
        "base_cost": Decimal("0.02"),
    },
    "linkup": {
        "env_var": "LINKUP_API_KEY",
        "server_type": ServerType.PYTHON,
        "package": "mcp-search-linkup",
        "tool_name": "linkup_search_web",
        "timeout": 10000,
        # Python module execution
        "args": ["-m", "mcp_search_linkup"],
        # Rate limits
        "rate_limits": RateLimitConfig(
            requests_per_minute=60,
            requests_per_hour=600,
            requests_per_day=5000,
            concurrent_requests=15,
        ),
        # Budget config
        "budget": BudgetConfig(
            default_query_budget=Decimal("0.01"),
            daily_budget=Decimal("5.00"),
            monthly_budget=Decimal("100.00"),
        ),
        # Base cost in USD per query
        "base_cost": Decimal("0.005"),
    },
    "perplexity": {
        "env_var": "PERPLEXITY_API_KEY",
        "server_type": ServerType.NODE_JS,
        "package": "@ppl-ai/perplexity-mcp",
        "tool_name": "perplexity_ask",
        "timeout": 20000,
        "args": ["perplexity-mcp"],
        # Rate limits
        "rate_limits": RateLimitConfig(
            requests_per_minute=30,
            requests_per_hour=300,
            requests_per_day=1000,
            concurrent_requests=5,
        ),
        # Budget config
        "budget": BudgetConfig(
            default_query_budget=Decimal("0.05"),
            daily_budget=Decimal("20.00"),
            monthly_budget=Decimal("200.00"),
        ),
        # Base cost in USD per query
        "base_cost": Decimal("0.025"),
    },
    "tavily": {
        "env_var": "TAVILY_API_KEY",
        "server_type": ServerType.NODE_JS,
        "package": "tavily-mcp@0.2.0",
        "tool_name": "tavily_search",
        "timeout": 10000,
        "args": ["tavily-mcp@0.2.0"],
        # Rate limits
        "rate_limits": RateLimitConfig(
            requests_per_minute=40,
            requests_per_hour=400,
            requests_per_day=4000,
            concurrent_requests=8,
        ),
        # Budget config
        "budget": BudgetConfig(
            default_query_budget=Decimal("0.03"),
            daily_budget=Decimal("10.00"),
            monthly_budget=Decimal("150.00"),
        ),
        # Base cost in USD per query
        "base_cost": Decimal("0.015"),
    },
}
