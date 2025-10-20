# Back-Compatibility Inventory & Kill Plan

The current codebase contains numerous legacy shims and unused abstractions. This plan enumerates each identified compatibility artifact and the steps to converge on a single modern implementation aligned with FastMCP 2.3.

## Inventory

| Artifact | Location | Description | Current Callers | Action |
|----------|----------|-------------|-----------------|--------|
| Legacy provider base (`BaseMCPProvider`, `GenericMCPProvider`) | `mcp_search_hub/providers/base_mcp.py`, `generic_mcp.py` | Custom stdio client, retry, rate limiting, and budget wrappers duplicating FastMCP provider orchestration | All provider subclasses (`exa_mcp`, `firecrawl_mcp`, `linkup_mcp`, `perplexity_mcp`, `tavily_mcp`) | Replace with FastMCP's built-in MCP client support (`fastmcp.client.AsyncMCPClient`); delete custom wrappers after migrating providers |
| Retry mixin references | Tests expect `mcp_search_hub.providers.retry_mixin` | Legacy module removed but tests still reference | `tests/test_retry.py` | Delete references; use FastMCP retry utilities or `fastmcp.contrib.retry` |
| Middleware custom stack | `mcp_search_hub/middleware/*` | Duplicates FastMCP's middleware interface; tests instantiate classes directly without Starlette `app` | HTTP pipeline | Adopt FastMCP HTTP middleware registration; remove bespoke middleware classes where built-ins exist |
| Result models duplication | `mcp_search_hub/models/results.py`, `models/router.py` | Custom dataclasses replicating FastMCP response payloads | Server routes, tests | Align with FastMCP tool schemas; remove redundant wrappers |
| Routing strategy flags | `query_routing` modules contain `execution_strategy`, `llm_routing_enabled`, `advanced` flags | Old cascaded router toggles | Router + tests | Collapse to a single routing strategy driven by FastMCP's skill tags; remove flags |
| Cache fingerprint toggles | `SearchCache.fingerprint_enabled` | Legacy flag gating semantic hashing | Cache pipeline | Decide canonical behavior (likely always on); remove flag |

## Kill Steps

1. **Providers**
   - [x] Introduce FastMCP-native provider client (one class) using `fastmcp.client.AsyncMCPClient`.
   - [x] Refactor provider modules to simple data/config definitions.
   - [x] Delete `BaseMCPProvider`, `GenericMCPProvider`, retry/budget/rate limit shims once all providers migrated.
   - [x] Update tests to use FastMCP mocks.

2. **Middleware**
   - [x] Use FastMCP's HTTP middleware registration via `FastMCP.http_app.add_middleware` wrappers.
   - [x] Replace custom logging/rate limit/auth/retry with FastMCP built-ins (review FastMCP 2.3 release notes).
   - [x] Remove tests relying on custom middleware internals; replace with FastMCP integration tests.

3. **Routing Flags**
   - [x] Audit `execution_strategy`, `advanced`, `routing_hints` parameters; confirm canonical API.
   - [x] Consolidate into FastMCP's `Context` metadata and provider tagging.
   - [x] Update documentation and tests accordingly.

4. **Models**
   - [x] Replace custom `SearchResponse`/`CombinedSearchResponse` with FastMCP `ToolResponse` dataclasses where possible.
   - [x] Maintain compatibility by generating Pydantic models with same schema until migration complete; document changes in `MIGRATION.md`.

5. **Cache Configuration**
   - [x] If semantic fingerprinting remains required, relocate to FastMCP's caching plugin (if available) or a single canonical implementation; remove `fingerprint_enabled` toggle.

## Rollout & Migration Notes

- Execute module by module to keep diffs reviewable.
- For each removal, update tests to use the new canonical API and ensure docs reference the modern path.
- `MIGRATION.md` should include import rewrites (e.g., `from mcp_search_hub.providers.base import SearchProvider` → `from fastmcp.contrib.providers import AsyncMCPProvider`).
- Validate with pytest suite once provider mocks updated; ensure coverage metrics stay above thresholds.

## Rollback Plan

- Maintain a branch with legacy providers until FastMCP-based replacements pass integration tests.
- Reintroduce removed modules temporarily by reverting the commit if migration blocks production deployment.

All compatibility artifacts should be removed in the first major refactor PR, accompanied by documentation updates and clear release notes.
