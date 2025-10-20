# Migration Guide: FastMCP 2.12 Modernization

This release replaces the bespoke provider/middleware stack with first-class FastMCP 2.12 primitives. Follow the steps below to upgrade.

## Highlights
- Providers now use `fastmcp.client.Client`; configure transports via `AppSettings` provider sections.
- `SearchServer` exposes only FastMCP-native middleware (`LoggingMiddleware`, `RetryMiddleware`, `SlidingWindowRateLimitingMiddleware`).
- Caching and metrics moved to `mcp_search_hub.cache.SearchCache` and `mcp_search_hub.metrics.MetricsTracker`.
- Routing and result aggregation rewritten under `mcp_search_hub.routing` and `mcp_search_hub.orchestrator`.

## Breaking Changes
- Removed modules: `mcp_search_hub/providers/base.py`, `generic_mcp.py`, `middleware/*`, `query_routing/*`, `result_processing/*`, and `utils/*`.
- Configuration flags `execution_strategy`, `llm_routing_enabled`, and `cache.fingerprint_enabled` no longer exist.
- Dependency footprint trimmed; ensure your environment installs from the refreshed `pyproject.toml` or `requirements.txt`.

## Upgrade Steps
1. **Install new dependencies**
   ```bash
   uv sync
   ```
2. **Update configuration**
   - Ensure provider entries define either `transport` (string or MCP config) or `command` arrays.
   - Remove deprecated routing and cache flags from `.env` or environment variables.
3. **Adopt new API surfaces**
   - Import `SearchServer` and `SearchQuery` from the top-level modules (`mcp_search_hub.server`, `mcp_search_hub.models`).
   - Use `SearchCache` and `MetricsTracker` where custom cache/metrics hooks were previously injected.
4. **Regenerate documentation**
   - `README.md` already reflects the FastMCP 2.12 baseline; mirror custom deployment notes as needed.

## Testing
Run the updated test suite to validate your deployment:
```bash
uv run pytest -q
```

For questions or issues, open a GitHub discussion or issue with the new configuration snippet.
