# Migration to 1.0

Version 1.0 is a hard cut. It has no compatibility layer for the unreleased v2-era architecture.

## Removed

- hard-coded Linkup, Exa, Perplexity, Tavily, and Firecrawl settings
- provider-specific `advanced` arguments
- custom Redis and memory caches
- custom metrics endpoint and middleware
- artificial intelligence (AI) query classification, cascade routing, and provider quality heuristics
- embedded provider installation and Docker Compose deployment

## Required changes

1. Define each downstream Model Context Protocol (MCP) server in the `PROVIDERS` JSON setting.
2. Declare its tool arguments, result path, and result field aliases.
3. Replace `advanced` with provider `static_arguments` in deployment config.
4. Read provenance from each result’s `sources` list.
5. Use `failed_providers` and `timed_out_providers` for partial-result handling.
6. Use `budget_usd` and `timeout_seconds` on each request when defaults are not sufficient.

The prior code was an unreleased internal draft, so version 1.0 retains no previous on-disk state or public wire contract.
