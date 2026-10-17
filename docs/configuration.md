# Configuration

Settings use Pydantic Settings. Nested environment keys use `__`, and `PROVIDERS` is a JSON object.

## Application settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `APP_NAME` | `MCP Search Hub` | MCP server display name |
| `ENVIRONMENT` | `development` | `development`, `test`, `staging`, or `production` |
| `TRANSPORT` | `stdio` | `stdio` or `http` |
| `HOST` | `127.0.0.1` | HTTP bind host |
| `PORT` | `8000` | HTTP bind port |
| `HTTP_PATH` | `/mcp` | MCP endpoint path; keep `/health` free for the health route |
| `LOG_LEVEL` | `INFO` | Python/FastMCP log level |
| `AUTH_TOKENS` | `[]` | Unique, nonblank static bearer tokens without surrounding whitespace |
| `PROVIDERS` | `{}` | Provider definitions keyed by identifier |
| `ROUTER__MAX_PROVIDERS` | `3` | Maximum selected providers |
| `ROUTER__DEFAULT_TIMEOUT_SECONDS` | `20` | Default request timeout |
| `ROUTER__DEFAULT_BUDGET_USD` | unset | Default estimated cost ceiling |
| `RESULTS__MAX_RESULTS` | `20` | Cap applied to downstream provider limits and final output |
| `RESULTS__RECIPROCAL_RANK_K` | `60` | RRF constant |
| `MIDDLEWARE__RATE_LIMIT_REQUESTS` | `120` | Requests per token/window; unauthenticated traffic shares one bucket |
| `MIDDLEWARE__RATE_LIMIT_WINDOW_MINUTES` | `1` | Sliding-window length |
| `MIDDLEWARE__INCLUDE_LOG_PAYLOADS` | `false` | Include MCP payloads in structured logs |

`HTTP_PATH` accepts a literal normalized path only: query strings, fragments, percent-encoded characters, and dot segments fail configuration. `run_http()` revalidates that every non-loopback bind has at least one `AUTH_TOKENS` entry, even when the process started with `TRANSPORT=stdio`.

## Provider fields

| Field | Meaning |
| --- | --- |
| `enabled` | Include or exclude the provider without deleting its configuration |
| `transport` | URL or FastMCP MCP configuration mapping |
| `command` | Executable followed by arguments for a stdio provider |
| `env` | Stdio subprocess environment; values may be exact `$NAME` references |
| `tool` | Downstream MCP tool name |
| `tags`, `weight` | Deterministic automatic-routing inputs |
| `timeout_seconds` | Provider cap applied by the orchestrator |
| `estimated_cost_usd` | Planner cost estimate for one request |
| `*_argument` | Downstream names for query, limit, and raw-content flags |
| `query_as_list` | `false` by default; `true` sends the query as a one-element string array |
| `static_arguments` | Deployment-owned constant tool arguments |
| `result_path` | String/integer path from the provider response to result items |
| `field_aliases` | Canonical title/URL/snippet/score/raw-content mappings |

Enabled providers require exactly one of `transport` or `command`. `env` is valid only with `command`; remote headers belong in a transport mapping.

Transport strings, command executables, tool names, and argument names must be nonblank and free of surrounding whitespace. Dynamic argument names must be unique and cannot overlap `static_arguments`. Transport mappings must contain at least one field, provider weights must be finite positive numbers, and unknown fields in provider, router, result, or middleware objects fail configuration.

Partial `field_aliases` mappings inherit defaults for omitted canonical fields. Alias lists must contain at least one trimmed name. The hub returns only declared canonical result fields and does not forward undeclared provider fields as metadata.

Result text fields (title, URL, snippet, and raw content) accept strings or arrays of strings. Arrays are joined with newlines, omitting blank entries; empty arrays become absent text. Other values retain their string conversion. This makes excerpt arrays readable without a provider-specific adapter.

See the [Parallel Search MCP setup](parallel.md) for an array-query provider example.

The resolver expands an exact `$NAME` string recursively in transports, stdio env, and static arguments. Missing names fail configuration. Resolved transport URLs and command executables must remain nonblank and trimmed. The resolver leaves strings that contain `$NAME` unchanged, which avoids implicit interpolation rules.
