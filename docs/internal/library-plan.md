# Library Change Plan

Date: 2025-10-19

## Summary of Findings

- **FastMCP** latest release is `2.12.5` (current requirement `>=2.3.5`). The project must target 2.12.x to leverage new provider orchestration, middleware, and tool definition helpers introduced since 2.5. 【0f9261†L1-L5】
- Multiple heavyweight dependencies (torch, sentence-transformers, onnx, onnxruntime, openvino) are declared but unused. 【5efab3†L31-L44】
- Core runtime imports `fastapi` and `starlette` transitively via FastMCP; Deptry flags them as missing direct dependencies. 【5efab3†L23-L30】
- Security tooling flagged MD5 usage and insecure PRNG in our wrappers; FastMCP 2.10+ exposes `fastmcp.utilities.cache.fingerprint` and `fastmcp.utilities.retry` that can replace custom logic.

## Proposed Library Actions (Decision Framework)

| Option | Leverage (35%) | Value (30%) | Load (25%) | Adapt (10%) | Total |
|--------|----------------|-------------|------------|-------------|-------|
| A. Upgrade to FastMCP 2.12.5 and replace custom providers with `fastmcp.client.AsyncMCPClient` | 35 | 28 | 15 | 9 | **87** |
| B. Retain custom provider stack on FastMCP 2.3.x | 10 | 12 | 20 | 8 | **50** |

**Rationale**: Upgrading unlocks built-in provider orchestration, HTTP middleware, and tool schemas, eliminating ~1.5k LOC of bespoke code (high leverage) while aligning with documented features (high value). Maintenance load drops by consolidating around library defaults; adaptability remains high because FastMCP now offers plugin APIs for custom routing.

| Option | Leverage | Value | Load | Adapt | Total |
|--------|----------|-------|------|-------|-------|
| C. Remove unused heavy ML dependencies (torch/onnx/openvino) | 32 | 20 | 20 | 8 | **80** |
| D. Keep current dependency list | 5 | 10 | 15 | 5 | **35** |

**Rationale**: Eliminating unused packages reduces install size (>1.7GB) and attack surface with no feature loss.

## Migration Steps

1. **FastMCP Upgrade**
   - [x] Update `pyproject.toml` to require `fastmcp>=2.12.5`.
   - [x] Review release notes 2.4→2.12 for breaking changes; adopt new APIs (tool decorators, provider registry, HTTP middleware).
   - [x] Replace `BaseMCPProvider` with wrappers around `FastMCPProvider`/`AsyncMCPClient`.
   - [x] Rewire server to use `FastMCP.create_http_app()` and library-provided routes instead of custom ones.

2. **Dependency Cleanup**
   - [x] Remove `torch`, `sentence-transformers`, `onnx`, `onnxruntime`, `openvino`, `circuitbreaker`, `diskcache` unless re-justified.
   - [x] Add missing direct dependencies (`fastapi`, `starlette`) if still referenced post-upgrade.
   - [x] Sync `uv.lock` via `uv lock`.

3. **Retry/Caching Modernization**
   - [x] Use `fastmcp.utilities.retry.retry_async` and `fastmcp.cache` features to replace custom modules flagged by Bandit.
   - [x] Migrate `SearchCache` to FastMCP's caching plugin (if available) or adapt to use `fastmcp.contrib.caching.RedisCache`.

4. **Documentation**
   - [x] Update README and docs to state FastMCP 2.12 baseline.
   - [x] Provide migration notes for removed dependencies and modules.

## Risk & Rollback

- Create staging branch; run full test suite with upgraded FastMCP.
- Rollback by pinning to 2.3.x and restoring provider wrappers if blocking issues arise.

This plan ensures the codebase aligns with the latest FastMCP capabilities while dramatically reducing custom maintenance burden.
