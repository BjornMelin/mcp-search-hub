# Architecture

The hub has four runtime steps:

1. `ProviderRegistry` resolves configuration and owns downstream Model Context Protocol (MCP) client lifecycle through the FastMCP server lifespan.
2. `RoutingPlanner` validates explicit provider lists or ranks providers by tag overlap and configured weight. It owns estimated request cost and rejects impossible budgets.
3. `SearchOrchestrator` starts all selected calls concurrently. It owns the request timeout, applies provider timeout caps, cancels pending calls, and returns successful, failed, and timed-out provider sets.
4. `fuse_results` canonicalizes URL/title identity and computes `sum(1 / (k + rank))`. Each contribution remains visible in `sources`.

FastMCP owns protocol handling, server lifecycle, static bearer-token verification, structured request logs, authenticated-client rate limits, and a shared unauthenticated sliding-window bucket. Search responses are not cached because native cache middleware cannot distinguish complete results from transient partial failures. No parallel custom implementation owns those concerns.

## Ownership boundaries

- Search Hub searches; it does not crawl or ingest.
- Provider MCP servers own vendor APIs and credentials.
- Deployment configuration owns provider argument/result mapping.
- The planner owns selection and estimated cost.
- The orchestrator owns time and concurrency.
- Reciprocal-rank fusion (RRF) sources are the canonical provenance record.

## Failure behavior

Unknown explicit providers, oversized explicit provider sets, and impossible budgets fail before provider lifecycle work begins. Runtime provider errors and timeouts produce partial responses. A provider timeout or caller-cancelled in-flight call quarantines the provider until old operations drain and a bounded client reset succeeds.

Operation generations prevent late completion from restoring health or invoking a recovered client. The registry owns at most one recovery task per unavailable provider. Automatic routes continue through ready providers instead of waiting for stalled recovery. An explicit route executes ready requested providers. It classifies unavailable peers from their completed or pending lifecycle state.

Startup responses distinguish completed failures from recoveries still pending at the request deadline. Registry shutdown never waits indefinitely for a cancellation-resistant downstream lifespan. Logs and responses include only error types; the hub never emits raw exception messages.
