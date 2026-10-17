# Parallel Search MCP

Use [Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp) as an opt-in downstream search provider. The anonymous endpoint provides free web search in Fast mode without an account or API key, subject to free-tier rate limits. This example uses the hub's generic provider configuration; it does not enable a provider by default.

## Configure a new hub

From the repository root, with Python 3.11–3.13 and uv 0.11.28 or newer:

```bash
uv sync --frozen --no-dev
export PARALLEL_SEARCH_SESSION_ID="$(uv run --no-sync python -c 'import uuid; print(uuid.uuid4())')"
export PROVIDERS="$(cat examples/parallel.json)"
uv run --no-sync mcp-search-hub
```

This starts the hub over stdio for an MCP client. The provider connects over Streamable HTTP. No additional server process or credentials are needed. Keep `PARALLEL_SEARCH_SESSION_ID` stable for related searches in one conversation, and generate a new value for a new conversation. Missing environment references fail configuration.

For an existing deployment, merge the `parallel` entry from [examples/parallel.json](../examples/parallel.json) into your provider map instead of replacing it. Explicitly request `providers: ["parallel"]` to use only this provider. Once enabled, it is also eligible for automatic routing alongside other enabled providers. Set `enabled` to `false` to keep the entry without using it.

## Run a search

With the same environment exports, run this instead of starting the stdio process to call the hub's public MCP tool in process:

```bash
uv run --no-sync python - <<'PY'
import asyncio
import json

from fastmcp import Client
from mcp_search_hub.config import AppSettings
from mcp_search_hub.server import SearchServer


async def main():
    server = SearchServer(AppSettings())
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "search",
            {
                "query": "FastMCP Streamable HTTP client configuration",
                "providers": ["parallel"],
                "max_results": 3,
            },
        )
        print(json.dumps(result.structured_content, indent=2))


asyncio.run(main())
PY
```

Successful responses include titles, URLs, newline-joined excerpts in `snippet`, and `sources` identifying `parallel` with each result's original rank. Check `successful_providers`, `failed_providers`, and `timed_out_providers` before using a partial response. Rate limits or provider errors can leave this single-provider search without results.

## Mapping details

- `query_as_list: true` wraps the hub query in an array for `web_search.search_queries`; `static_arguments.objective` supplies the required search objective. Use a concise keyword query, and customize the objective for a focused deployment.
- `max_results_argument: null` and `raw_content_argument: null` omit parameters that `web_search` does not accept. The hub still caps returned results locally. `include_raw_content` does not fetch full pages with this configuration.
- `result_path` selects `results`, and the `snippet` alias maps the provider's `excerpts` string array to readable text. Default title and URL aliases remain in effect.
- The transport sets a project User-Agent and sends no authorization header. The default cost estimate is zero for anonymous use; it is a routing estimate, not a quota guarantee. If you configure paid authentication, also set `estimated_cost_usd` to match your deployment.

The hub remains search-only. This example does not expose Parallel's `web_fetch` tool or add a crawling step. See the [configuration reference](configuration.md) for the generic provider contract.
