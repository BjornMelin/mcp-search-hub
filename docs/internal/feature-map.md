# Feature Map

This document catalogs the externally documented behaviors of MCP Search Hub and maps them to the FastMCP-first modules that implement them. Items marked **UNVERIFIED** require additional evidence (tests, docs, or manual validation) to confirm end-to-end wiring.

## Core Server Features

| Feature | Description | Owning Modules | Public Surface | Inputs | Outputs | Side Effects | Acceptance Criteria |
|---------|-------------|----------------|----------------|--------|---------|--------------|---------------------|
| Unified MCP server | Expose a single FastMCP server that aggregates all provider tools. | `mcp_search_hub.server.SearchServer`, `mcp_search_hub.server.StaticTokenVerifier` | `SearchServer.mcp`, `SearchServer.http_app`, CLI entry point (`python -m mcp_search_hub.main`) | FastMCP start arguments, env config | Starlette ASGI app, MCP transport endpoints | Configures middleware, registers tools | ✅ Verified by `tests/test_server.py::test_server_health_and_metrics` (FastMCP boot, `/health`, `/metrics`, tool discovery). |
| Intelligent routing | Analyze queries and select providers based on heuristics and tags. | `mcp_search_hub.routing.classifier.QueryClassifier`, `mcp_search_hub.routing.planner.RoutingPlanner` | `QueryClassifier.classify_intent`, `.infer_tags`; `RoutingPlanner.plan` | `SearchQuery`, provider metadata | Routing plan with selected providers | Reads provider tags/weights | ✅ Covered by `tests/test_routing.py` (intent tagging and provider selection heuristics). |
| Provider orchestration | Coordinate provider lifecycle and search execution. | `mcp_search_hub.orchestrator.SearchOrchestrator`, `mcp_search_hub.providers.registry.ProviderRegistry`, `mcp_search_hub.providers.sessions.MCPProviderSession` | `SearchOrchestrator.execute`, `ProviderRegistry.startup/ensure_started`, `MCPProviderSession.call_search` | Query payload, provider configs | Provider search results, orchestration metadata | Spawns MCP client sessions, updates metrics/cache | ⚠️ PARTIAL - `tests/test_orchestrator.py` covers orchestrator caching with stub sessions; integration coverage for `MCPProviderSession` lifecycle and failure handling is still missing. |
| Result merging | Deduplicate and rank provider results. | `mcp_search_hub.orchestrator.SearchOrchestrator._merge` | `_merge`, `_parse_results` helpers | Provider `CallToolResult` payloads | `CombinedSearchResponse` | Updates metrics/cache | **UNVERIFIED** Deterministic tests for deduplication, score ordering, and metadata merging not yet in place. |
| Tiered caching | Memory + Redis caching for search responses. | `mcp_search_hub.cache.SearchCache` | `SearchCache.get`, `SearchCache.set`, `SearchCache.invalidate` | Cache keys derived from query fingerprint | Cached search response data | Interacts with Redis when configured | ⚠️ PARTIAL - `tests/test_cache.py` exercises in-memory caching; Redis TTL/jitter behaviour remains untested. |
| Metrics/observability | Emit metrics and health information. | `mcp_search_hub.metrics.MetricsTracker`, `mcp_search_hub.server.SearchServer._metrics_route` | `/metrics` HTTP endpoint, `MetricsTracker.record_*` | Search execution metadata | JSON metrics payload | Uses in-memory counters | ✅ Verified by `tests/test_orchestrator.py::test_orchestrator_executes_and_caches` and `tests/test_server.py::test_server_health_and_metrics`. |
| Health reporting | Report provider and hub health. | `mcp_search_hub.server.SearchServer.health`, `mcp_search_hub.providers.registry.ProviderRegistry.health` | `/health` route, `SearchServer.health` | HTTP GET, provider health snapshots | `HealthResponse` JSON | Reads provider status cache | ✅ `tests/test_server.py::test_server_health_and_metrics` asserts aggregated provider counts/schema. |
| Authentication & rate limiting | Control HTTP access and throughput via middleware. | `mcp_search_hub.server.SearchServer._configure_middleware`, `_build_http_middleware` | FastMCP middleware stack (`LoggingMiddleware`, `RetryMiddleware`, `SlidingWindowRateLimitingMiddleware`, `StaticTokenVerifier.get_middleware`) | HTTP headers, request path | Permit/deny HTTP request | Logs requests, enforces rate limit | **UNVERIFIED** No automated coverage for auth/rate-limit toggles or retry middleware configuration. |
| Tool catalog exposure | Surface provider tools through FastMCP. | `mcp_search_hub.server.SearchServer._register_tools`, `SearchServer.provider_catalog` | FastMCP tool registry (`search`, `get_provider_info`) | Provider definitions | Registered tool definitions, provider metadata | None | ✅ `tests/test_server.py::test_server_health_and_metrics` validates tool registration and catalog export. |

## Auxiliary Features

| Feature | Description | Modules | Notes | Acceptance |
|---------|-------------|---------|-------|------------|
| Configuration management | Nested Pydantic settings with env overrides | `mcp_search_hub.config.settings.AppSettings`, `mcp_search_hub.config.settings.get_settings` | Leverages Pydantic Settings v2 with cached accessor | **UNVERIFIED** Add tests ensuring env overrides and `get_settings()` caching. |
| Budget tracking | Track per-provider spend | _Not implemented in FastMCP refactor_ | Legacy budget tracker was removed alongside old orchestrator | **UNVERIFIED** Decide whether to reintroduce spend tracking via `ProviderSession` metadata. |
| Rate limiting per provider | Rate limit provider usage | _Not implemented in FastMCP refactor_ | Only global HTTP throttling remains in `SearchServer._configure_middleware` | **UNVERIFIED** Design per-provider limiter compatible with FastMCP clients. |
| Retry logic | FastMCP retry middleware guards tool execution | `mcp_search_hub.server.SearchServer._configure_middleware` (FastMCP `RetryMiddleware`) | Config-driven retries replace bespoke wrappers | **UNVERIFIED** Add tests covering retry configuration paths and failure telemetry. |
| OpenAPI schema | FastMCP-generated OpenAPI docs for HTTP transport | FastMCP HTTP app (no custom override) | `/docs` served directly by FastMCP | **UNVERIFIED** Manual check or automated smoke test needed to confirm schema availability. |
| CLI setup script | Configure Claude Desktop integration | `scripts/setup_claude_desktop.py` | Guides API key setup | **UNVERIFIED** No automated coverage for interactive script paths. |

## Tool Catalogue Snapshot (Docs Reference)

- Core: `search`, `get_provider_info`
- Firecrawl: `firecrawl_scrape`, `firecrawl_search`, `firecrawl_crawl`, `firecrawl_extract`
- Exa: `web_search_exa`, `research_paper_search`, `company_research`, `linkedin_search`
- Perplexity: `perplexity_ask`, `perplexity_research`
- Linkup: `linkup_search_web`
- Tavily: `tavily_search`, `tavily_extract`

## Acceptance Criteria Summary

1. `mcp_search_hub.server.SearchServer` must boot with FastMCP 2.x, expose `/health` and `/metrics`, and register hub + provider tools.
2. `mcp_search_hub.routing` must route queries based on classifier tags and provider weights, with routing metadata returned in responses.
3. `mcp_search_hub.orchestrator` + `providers` must manage provider lifecycles, retries, and any spend/rate controls needed for resilience.
4. `SearchOrchestrator._merge` must produce deterministic ordering, deduplicate by URL/title/snippet, and retain provenance metadata.
5. `SearchCache` must honor memory + Redis tiers with configurable TTL and jitter.
6. `SearchServer._configure_middleware` must enforce auth, rate limits, retries, and structured logging when enabled.
7. `MetricsTracker` + `/metrics` must reflect provider states, cache hits, and request statistics.
8. `AppSettings` must respect environment overrides for providers, middleware, cache, and transport knobs.

## Follow-up Tasks

- Add integration tests in `tests/test_orchestrator.py` (or new suite) that exercise `MCPProviderSession` startup/shutdown, failure thresholds, and retry wiring end-to-end. **(Provider orchestration – ⚠️ PARTIAL)**
- Create deterministic result-merging tests covering duplicate URLs/titles and score ordering within `SearchOrchestrator._merge`. **(Result merging – UNVERIFIED)**
- Extend cache coverage with Redis-enabled tests (e.g., using `fakeredis` or dockerised Redis) to validate TTL + jitter handling in `SearchCache`. **(Tiered caching – ⚠️ PARTIAL)**
- Introduce middleware toggle tests for auth, rate limiting, and retry configuration within `SearchServer._configure_middleware` / `_build_http_middleware`. **(Authentication & rate limiting – UNVERIFIED)**
- Implement settings override tests ensuring `AppSettings` picks up environment variables and `get_settings()` caching semantics. **(Configuration management – UNVERIFIED)**
- Define a FastMCP-native budget tracking or document deprecation; if retained, implement via `ProviderSession` metadata with automated tests. **(Budget tracking – UNVERIFIED)**
- Design and test per-provider rate limiting compatible with FastMCP client sessions, or explicitly de-scope it. **(Rate limiting per provider – UNVERIFIED)**
- Add regression coverage confirming FastMCP-generated `/docs` responds successfully in HTTP mode. **(OpenAPI schema – UNVERIFIED)**
- Provide automated smoke coverage (or script tests) for `scripts/setup_claude_desktop.py` to ensure onboarding flow remains valid. **(CLI setup script – UNVERIFIED)**
