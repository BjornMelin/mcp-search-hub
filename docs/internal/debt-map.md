# Technical Debt Map

This table consolidates findings from static analyzers, type checkers, security scans, dependency audits, and tests executed on 2025-10-19.

| File/Area | Issue | Category | Impact | Recommended Action | Evidence |
|-----------|-------|----------|--------|--------------------|----------|
| `mcp_search_hub/main.py` | Unused variable `s` flagged by Vulture | Dead code | Low | Remove unused variable to reduce noise | `uv run --with vulture==2.7 vulture mcp_search_hub --min-confidence 80` (`c702ce†L1-L9`)
| `mcp_search_hub/middleware/rate_limit.py` | Unused variable `identifier` | Dead code | Low | Remove unused variable | `c702ce†L2-L3`
| `mcp_search_hub/models/interfaces.py` | Unused locals `selected_providers`, `result_stream` | Dead code | Medium | Delete unused variables; verify interface coverage | `c702ce†L3-L4`
| `mcp_search_hub/providers/base_mcp.py` | Multiple unused exception vars in context manager | Dead code | Low | Replace with `_` placeholders | `c702ce†L5-L7`
| `mcp_search_hub/query_routing/performance_tracker.py` | Unused exception vars | Dead code | Low | Replace with `_` placeholders | `c702ce†L7-L8`
| `mcp_search_hub/experimentation/ab_testing.py` | MD5 usage, insecure random, magic numbers flagged by Bandit & Ruff | Security / Style | High | Replace with SHA256 (non-security-critical? mark UNVERIFIED), use secrets.randbelow, extract constants | `0db004†L12-L77`, `4a8f9f†L5-L14`
| Middleware modules (`logging.py`, `rate_limit.py`, `retry.py`) | Magic numbers, complex functions, insecure random jitter | Complexity / Security | Medium | Extract constants, refactor to simpler primitives, adopt FastMCP middleware hooks | `4a8f9f†L14-L48`, `0db004†L78-L115`
| `providers/base_mcp.py` | Excessive arguments/returns, inline imports, subprocess usage flagged by Bandit and Ruff | Complexity / Security | High | Evaluate replacing with FastMCP native MCP client support; centralize subprocess management | `4a8f9f†L23-L44`, `0db004†L112-L128`
| `query_routing/analyzer.py` | High cyclomatic complexity and branching | Complexity | High | Refactor into modular scorers; consider leveraging FastMCP query classification features | `4a8f9f†L49-L73`
| `result_processing/metadata_enrichment.py` | Too many statements & magic numbers | Complexity | Medium | Break into helper functions; move thresholds to config | `4a8f9f†L74-L110`
| `server.py` | Many Ruff lint issues (branching, inline imports, attribute assumptions); type errors flagged by Pyright; FastMCP tool registration fails due to missing type hints; `/metrics` manipulates typed models incorrectly | Complexity / Correctness | Critical | Rewrite around FastMCP 2.3 tool registration helpers; ensure type hints import `Context`; restructure metrics handling | `4a8f9f†L111-L163`, `23ab07†L39-L135`
| `utils/retry.py` | Excessive branching, insecure random jitter | Complexity / Security | Medium | Replace with FastMCP retry utilities; adopt deterministic jitter config | `4a8f9f†L164-L198`, `0db004†L116-L141`
| Dependency configuration (`pyproject.toml`) | Deptry flagged unused heavy dependencies (torch, sentence-transformers, etc.) and missing direct deps (fastapi) | Dependency hygiene | High | Audit dependency tree; remove unused heavy libs; add direct dependencies used by app | `5efab3†L12-L44`
| Tests | Pyright indicates numerous constructor mismatches due to outdated helper factories; pytest fails extensively due to SearchServer requiring API keys and missing type hints | Test debt | Critical | Refactor tests to work with FastMCP's injection hooks, provide provider mocks, and fix dataclass factories | `23ab07†L197-L287`, `ed8c78†L1-L126`
| Settings | Bandit flagged binding to `0.0.0.0` in defaults; evaluate environment-specific override | Security | Medium | Document or gate binding; allow override via env | `0db004†L5-L13`, `0db004†L125-L141`

## Summary

- **Critical**: `server.py` FastMCP integration errors; test suite broken; dependency bloat.
- **High**: Security findings around MD5 usage and subprocess management; query analyzer complexity.
- **Medium**: Middleware randomness, metadata enrichment thresholds, rate limiter API mismatches.
- **Low**: Miscellaneous unused variables from Vulture scan.

These issues must be prioritized in the refactor roadmap to ensure FastMCP leverage and maintainability.
