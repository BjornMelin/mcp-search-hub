# Feature Map

This document catalogs the externally documented behaviors of MCP Search Hub and maps them to the concrete modules that implement them. Items marked **UNVERIFIED** require additional evidence (tests, docs, or manual validation) to confirm end-to-end wiring.

## Core Server Features

| Feature | Description | Owning Modules | Public Surface | Inputs | Outputs | Side Effects | Acceptance Criteria |
|---------|-------------|----------------|----------------|--------|---------|--------------|---------------------|
| Unified MCP server | Expose a single FastMCP server that aggregates all provider tools. | `mcp_search_hub.server.SearchServer`, `mcp_search_hub.main.run` | `SearchServer.mcp` (FastMCP instance), CLI entry point (`python -m mcp_search_hub.main`) | FastMCP start arguments, env config | Starlette ASGI app, MCP transport endpoints | Starts FastMCP with middleware, registers tools | ✅ Server boots with FastMCP 2.x, `/health` returns 200, tooling discovery lists hub tools |
| Intelligent routing | Analyze queries and select providers based on heuristics and budgets. | `query_routing.analyzer`, `query_routing.hybrid_router` | `HybridRouter.route`, `QueryAnalyzer.analyze` | `SearchQuery`, provider metadata | Provider plan specifying selected providers | Reads provider metrics/cache | **UNVERIFIED** Need integration test verifying provider selection vs query types |
| Provider orchestration | Launch and talk to embedded provider MCP servers via stdio. | `providers.base_mcp.BaseMCPProvider` and subclasses | `SearchProvider.search`, `initialize`, provider-specific tool exposures | Query payload, provider configs | Provider search results | Spawns subprocesses, network calls, caches budgets | **UNVERIFIED** Provide mocked subprocess tests ensuring initialization lifecycle |
| Result merging | Deduplicate and rank provider results. | `result_processing.merger.ResultMerger` | `ResultMerger.merge` | List of provider `SearchResponse` objects | `CombinedSearchResponse` | Updates metrics, may cache | **UNVERIFIED** Need deterministic tests for dedupe + scoring |
| Tiered caching | Memory + Redis caching for search responses. | `utils.cache.SearchCache` | `SearchCache.get_or_set`, `SearchCache.invalidate` | Cache keys derived from query fingerprint | Cached search response data | Interacts with Redis | **UNVERIFIED** Need Redis integration/unit tests verifying TTL + jitter |
| Metrics/observability | Emit metrics and health information. | `utils.metrics.MetricsTracker`, `server._register_custom_routes` | `/metrics` HTTP endpoint, `MetricsTracker.record_*` methods | Search execution metadata | JSON metrics payload | Uses in-memory counters | ✅ Metrics endpoint returns JSON with provider stats |
| Health reporting | Report provider and hub health. | `server._register_custom_routes` | `/health` route | HTTP GET | `HealthResponse` JSON | Touches provider status cache | ✅ `/health` returns aggregated provider state with correct schema |
| Authentication & rate limiting | Control HTTP access and throughput via middleware. | `middleware` package | Starlette middleware classes | HTTP headers, request path | Permit/deny HTTP request | Logs requests, enforces rate limit | **UNVERIFIED** Need middleware tests covering auth, rate limit, retry |
| Tool catalog exposure | Surface provider tools through FastMCP. | `server._register_tools`, provider `register_tools` | MCP tool metadata via FastMCP | Provider definitions | Registered tool definitions | None | **UNVERIFIED** Need FastMCP-driven tests enumerating expected tools |

## Auxiliary Features

| Feature | Description | Modules | Notes | Acceptance |
|---------|-------------|---------|-------|------------|
| Configuration management | Nested Pydantic settings with env overrides | `config.settings`, `.env.template` | Leverages Pydantic Settings v2 | ✅ `get_settings()` returns cached settings, env overrides respected |
| Budget tracking | Track per-provider spend | `providers.budget_tracker` | Hooks into provider execution | **UNVERIFIED** Need test verifying budget enforcement |
| Rate limiting per provider | Rate limit provider usage | `providers.rate_limiter` | In-memory token bucket | **UNVERIFIED** Provide concurrency tests |
| Retry logic | Exponential backoff for provider calls | `utils.retry`, provider wrappers | Should align with FastMCP resilience features | **UNVERIFIED** Evaluate replacing with FastMCP retry support |
| OpenAPI schema | Customized OpenAPI docs for HTTP transport | `openapi.schema` | `/docs` route uses this | ✅ Schema generation uses FastMCP HTTP integration |
| CLI setup script | Configure Claude Desktop integration | `scripts/setup_claude_desktop.py` | Guides API key setup | ✅ Script prompts for required keys |

## Tool Catalogue Snapshot (Docs Reference)

- Core: `search`, `get_provider_info`
- Firecrawl: `firecrawl_scrape`, `firecrawl_search`, `firecrawl_crawl`, `firecrawl_extract`
- Exa: `web_search_exa`, `research_paper_search`, `company_research`, `linkedin_search`
- Perplexity: `perplexity_ask`, `perplexity_research`
- Linkup: `linkup_search_web`
- Tavily: `tavily_search`, `tavily_extract`

## Acceptance Criteria Summary

1. Hub must boot with FastMCP 2.x, expose `/health`, `/metrics`, and register hub + provider tools.
2. Queries are routed based on analyzer scores; routing decisions logged with provider rationale.
3. Provider subprocess lifecycle is resilient with retries, budget, and rate limiting.
4. Result merger returns deterministic ordering and deduplication across providers.
5. Cache honors memory + Redis tiers with configurable TTL + jitter.
6. Middleware enforces auth, rate limits, retries, and structured logging when enabled.
7. Metrics and health endpoints reflect provider states and request statistics.
8. Configuration via environment variables works for all providers, middleware, and cache knobs.

Areas marked **UNVERIFIED** require new or improved automated tests plus manual verification before declaring the feature preserved post-refactor.
