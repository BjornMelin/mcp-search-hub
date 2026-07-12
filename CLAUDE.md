# Repository guidance

MCP Search Hub is a Python 3.11–3.13 FastMCP 3.4.4 service managed with uv.

## Architecture rules

- Keep the service search-only. Crawling, ingestion, memory, and large language model routing belong in other repositories.
- Providers are data-driven `ProviderDefinition` records. Do not add provider-specific classes or hard-coded vendor names.
- `RoutingPlanner` is the only cost/selection owner.
- `SearchOrchestrator` is the only timeout/concurrency owner.
- Preserve reciprocal-rank fusion (RRF) provenance; never replace `sources` with a singular provider.
- Use FastMCP middleware/lifespan/auth primitives before adding custom code.
- Make contract changes forward-only; migrate all call sites and delete old shapes instead of adding compatibility paths.
- Update `README.md`, `docs/`, `.env.example`, and `examples/` with every public settings, tool, or result contract change.

## Required verification

```bash
uv sync --frozen --group dev
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python -m compileall -q mcp_search_hub tests
uv run python -m build
```
