# Changelog

## 1.0.0 - 2026-07-11

- Replaced the experimental provider-specific architecture with a generic FastMCP 3.4.4 provider contract.
- Added deterministic explicit/tag routing and request-cost enforcement.
- Added concurrent execution with one timeout owner and partial results.
- Added canonical deduplication, reciprocal-rank fusion, and typed provenance.
- Deleted custom cache, Redis, metrics, and ineffective retry layers; replaced auth, logging, and rate limiting with FastMCP-native capabilities.
- Removed unsupported benchmark, provider-quality, compatibility, Docker Compose, embedded-provider, and artificial intelligence routing claims.
- Added Python 3.11–3.13 CI, in-memory MCP protocol tests, and extracted source-distribution verification.
- Added fail-closed validation for HTTP mounts, authentication tokens, provider transports, unknown nested settings fields, tool-argument collisions, weights, and result scores.
- Added per-provider startup recovery and timeout quarantine so failed or cancellation-resistant calls cannot overlap a recovered client generation.
- Added lifecycle preflight, precise startup failure attribution, stale-operation fencing, and bounded recovery shutdown.
- Added constrained MCP input schemas, typed outputs, and exact decimal cost serialization.
- Added transport reconnection, fallback result aliases, and original provider-rank provenance.
