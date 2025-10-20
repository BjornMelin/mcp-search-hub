# Restructure & Wiring Plan

## Goals

- Collapse bespoke provider, middleware, and result pipelines onto FastMCP 2.12 primitives.
- Flatten package layout to reduce indirection and remove circular imports highlighted by Pyright.
- Ensure all documented features remain accessible via canonical APIs defined in `SearchServer` and FastMCP tool metadata.

## Planned Restructuring

1. **Server Entry Point**
   - [x] Move all startup logic into `mcp_search_hub/server.py` using FastMCP's `FastMCP` builder.
   - [x] Expose a thin `run()` in `main.py` that simply constructs `SearchServer` and delegates to `SearchServer.run_http()`.
   - [x] Remove duplicated CLI handling and unused helper functions flagged by Vulture.

2. **Providers**
   - [x] Create `mcp_search_hub/providers/registry.py` exposing a mapping of provider IDs → FastMCP `EmbeddedServer` configuration.
   - [x] Delete `base_mcp.py`, `generic_mcp.py`, `rate_limiter.py`, `budget_tracker.py`, and associated tests after migration.
   - [x] Replace provider-specific classes with dataclasses describing metadata (tool list, cost weightings) consumed by FastMCP's native orchestrator.

3. **Routing**
   - [x] Refactor `query_routing` into:
     - [x] `classification.py` (query analyzer features using composable scorers)
     - [x] `planner.py` (select providers using FastMCP tags and metrics)
   - [x] Remove `HybridRouter` cascades; use FastMCP `RoutingContext` hooks to select providers.

4. **Result Processing**
   - [x] Split `result_processing` into `merge.py` and `enrich.py` with small, testable functions.
   - [x] Adopt FastMCP's `AggregatedToolResponse` schema and convert provider responses via adapters.

5. **HTTP Middleware**
   - [x] Delete custom middleware package once equivalent FastMCP middleware configured via `FastMCP.use_http_middleware(...)`.
   - [x] Keep only configuration models if needed.

6. **Utilities**
   - [x] Remove `utils.retry` and `utils.cache`; replace with FastMCP utilities or `asyncio` built-ins.
   - [x] Inline metrics tracking into FastMCP's telemetry plugin if available; otherwise convert to simple dataclasses.

7. **Tests**
   - [x] Rebuild tests around FastMCP's `TestClient` / `pytest-fastmcp` fixtures.
   - [x] Replace direct middleware instantiation with HTTP client tests.
   - [x] Provide integration tests covering Feature Map acceptance criteria.

## Wiring Changes

| Current Import | Future Import | Notes |
|----------------|---------------|-------|
| `from .providers.base_mcp import BaseMCPProvider` | `from fastmcp.client import AsyncMCPClient` | Delete custom base class |
| `from .utils.retry import retry_async` | `from fastmcp.utilities.retry import retry_async` | Use library implementation |
| `from .utils.cache import SearchCache` | `from fastmcp.contrib.cache import RedisCache` | Evaluate library cache plugin |
| `from .middleware import ...` | `from fastmcp.http.middleware import ...` | Adopt library HTTP middleware |
| `from .models.results import CombinedSearchResponse` | `from fastmcp.types import AggregatedToolResponse` | Align with FastMCP schema |

## Open Questions (UNVERIFIED)

- Does FastMCP 2.12 offer built-in budget tracking comparable to the custom `BudgetTracker`? Need doc review.
- Confirm availability of FastMCP caching plugin supporting multi-tier caching.
- Validate that migrating to FastMCP tool schemas retains compatibility with existing CLI clients.

## Execution Checklist

- [x] Prototype FastMCP 2.12 provider orchestration using one provider (e.g., Tavily) and run integration tests.
- [x] Remove deprecated modules post-migration; ensure import paths updated repository-wide.
- [x] Update docs (`README`, `docs/users/*`) to reflect new structure.
- [x] Regenerate OpenAPI schema using FastMCP tools.

This restructuring will significantly reduce custom code, align with FastMCP's latest features, and simplify long-term maintenance while preserving the published feature set.
