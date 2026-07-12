# MCP Search Hub

MCP Search Hub runs one search request across configured downstream Model Context Protocol (MCP) servers. It selects providers deterministically, enforces request-level cost and timeout budgets, then combines results with reciprocal-rank fusion (RRF) and explicit source provenance.

The hub does not bundle search providers, crawl the web, score providers with a large language model (LLM), or manage provider credentials. Each provider is an MCP transport and a declarative result mapping supplied at deployment time.

## What MCP Search Hub includes

- FastMCP 3.4.4 lifecycle, bearer-token verification, structured logging, per-token rate limits, and one bounded unauthenticated rate-limit bucket
- concurrent provider calls under one orchestrator-owned timeout budget
- explicit provider selection or deterministic tag/weight routing
- optional estimated request-cost budget
- URL/title deduplication and standard RRF (`k=60` by default)
- per-result provider, original-rank, and original-score provenance
- stdio and Streamable HTTP transports

## Local development

Requires Python 3.11–3.13 and uv 0.11.28 or newer.

```bash
uv sync --frozen --group dev
uv run pytest
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run python -m compileall -q mcp_search_hub tests
uv run python -m build
```

Start with stdio (the default):

```bash
uv run mcp-search-hub
```

This starts an empty hub. Configure at least one provider before calling `search`.

Start the HTTP transport on loopback:

```bash
TRANSPORT=http uv run mcp-search-hub
```

Non-loopback HTTP binds fail closed unless `AUTH_TOKENS` contains at least one bearer token. Tokens must be nonblank, unique, and free of surrounding whitespace. For public production ingress, keep the hub on a private or loopback interface and terminate identity at a production authentication gateway. The built-in static tokens support constrained deployments.

## Provider configuration

`PROVIDERS` is a JSON object keyed by lowercase provider identifier. A provider uses either a remote `transport` or a local `command`, never both.

The values below are disabled placeholders. Replace the endpoint and credentials, then set `enabled` to `true`.

```json
{
  "docs": {
    "enabled": false,
    "transport": "https://example.com/mcp",
    "tool": "search",
    "tags": ["general", "technical"],
    "weight": 1.2,
    "timeout_seconds": 15,
    "estimated_cost_usd": "0.01",
    "query_argument": "query",
    "max_results_argument": "limit",
    "raw_content_argument": "include_content",
    "static_arguments": {"language": "en"},
    "result_path": ["results"],
    "field_aliases": {
      "title": ["title"],
      "url": ["url"],
      "snippet": ["description"],
      "score": ["score"],
      "raw_content": ["content"]
    }
  }
}
```

An exact string such as `$DOCS_API_KEY` resolves from the process environment and fails startup when missing. Partial interpolation is not supported. The hub passes transport mappings to FastMCP, so remote headers can use the same explicit reference form.

See the complete [configuration](https://github.com/BjornMelin/mcp-search-hub/blob/main/docs/configuration.md) and [architecture](https://github.com/BjornMelin/mcp-search-hub/blob/main/docs/architecture.md) contracts.

## MCP tools

`search` accepts:

- `query` (required)
- `max_results`
- `include_raw_content`
- `providers` (optional explicit whitelist)
- `tags` (optional routing hints)
- `timeout_seconds`
- `budget_usd`

The response names selected, successful, failed, and timed-out providers. Every fused result has a `sources` list with provider, original rank, and optional original score. The hub omits provider error text from caller responses.

`get_provider_info` returns non-secret tool, tag, weight, timeout, and estimated cost metadata. `GET /health` is available with the HTTP transport, so `HTTP_PATH` cannot be `/health`.

## License

MIT. See [LICENSE](https://github.com/BjornMelin/mcp-search-hub/blob/main/LICENSE).
