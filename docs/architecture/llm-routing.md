# LLM-Directed Query Routing

This document describes the LLM-directed query routing implementation in MCP Search Hub.

## Overview

MCP Search Hub now allows client LLMs to influence or control query routing decisions in two complementary ways:

1. **Explicit Routing Parameters**: Direct control through parameters like `providers` and `routing_strategy`
2. **Natural Language Routing Hints**: Indirect control through free-form guidance in the `routing_hints` parameter

Additionally, the system can use LLMs internally for routing decisions through the new `LLMQueryRouter`.

## Client Interface

### Explicit Routing Parameters

```python
{
  "query": "latest breakthroughs in quantum computing",
  "providers": ["perplexity", "tavily"],  # Explicit provider selection
  "routing_strategy": "cascade",  # Execution strategy: "parallel" or "cascade"
  "budget": 0.05,  # Maximum budget in USD
  "routing_hints": "prioritize academic sources and recent publications"  # Natural language guidance
}
```

### Natural Language Routing Hints

The `routing_hints` parameter accepts free-form text that provides guidance to the router without requiring explicit parameter knowledge:

```python
{
  "query": "latest breakthroughs in quantum computing",
  "routing_hints": "prioritize academic sources and recent publications"
}
```

The `RoutingHintParser` translates these hints into structured parameters:

| Common Hint Phrases | Effect |
|--|--|
| "academic", "research" | Prioritizes research-oriented providers (Perplexity, Exa) |
| "news", "recent" | Prioritizes real-time information providers (Tavily, Linkup) |
| "images", "visual" | Prioritizes providers with visual content (Firecrawl, Tavily) |
| "reliable", "thorough" | Uses cascade execution strategy with higher reliability |
| "fast", "quick" | Uses parallel execution strategy for faster response |

## Internal LLM Routing

The `LLMQueryRouter` uses an LLM (typically Perplexity) to score providers for complex queries:

1. For each query, the LLM evaluates which providers are most suitable based on query characteristics
2. The LLM provides scores, confidence, and recommended execution strategy
3. Results are cached to improve performance and reduce LLM API costs
4. Fallback to traditional scoring happens when LLM routing is disabled or fails

### Configuration

LLM routing is controlled through environment variables:

```bash
# Enable/disable LLM-based routing
LLM_ROUTER_ENABLED=true

# Complexity threshold to activate LLM routing (0.0-1.0)
LLM_ROUTER_THRESHOLD=0.5

# LLM provider for routing decisions
LLM_ROUTER_PROVIDER=perplexity

# Cache TTL for LLM routing decisions (seconds)
LLM_ROUTER_CACHE_TTL=3600
```

## Implementation Details

### Pluggable Scoring System

The `LLMQueryRouter` implements the `ProviderScorer` protocol from `unified_router.py`, fitting into the existing pluggable scoring system:

```python
def score_provider(
    self,
    provider_name: str,
    provider: SearchProvider,
    features: QueryFeatures,
    metrics: Optional[ProviderPerformanceMetrics] = None,
) -> ProviderScore:
    # Implementation...
```

### Query Processing Flow

1. Client submits a query with optional routing parameters and/or hints
2. If routing hints are provided, they're parsed into structured parameters
3. Explicit parameters take precedence over hints-derived parameters
4. The `UnifiedRouter` selects providers using traditional scoring and/or LLM scoring
5. The chosen execution strategy is applied to execute the search
6. Results are returned to the client

## Benefits

- **Flexibility**: Clients can use explicit parameters, natural language hints, or a combination
- **Progressive Enhancement**: Works with existing clients while offering advanced features to newer ones
- **Separation of Concerns**: Maintains clean architecture with pluggable components
- **Fallback Mechanisms**: Traditional routing remains available when LLM routing is inappropriate

## Example Usage

### Example 1: Basic Query (No LLM Direction)

```python
{
  "query": "weather in San Francisco"
}
```

The system uses its default routing logic for this simple query.

### Example 2: Explicit Parameters

```python
{
  "query": "impact of climate change on agriculture",
  "providers": ["perplexity", "exa"],
  "routing_strategy": "cascade"
}
```

The system uses the specified providers in cascade mode.

### Example 3: Natural Language Hints

```python
{
  "query": "latest COVID-19 research",
  "routing_hints": "need academic sources with recent publications on medical research"
}
```

The system prioritizes research-oriented providers and uses a cascade strategy for reliability.

### Example 4: Combined Approach

```python
{
  "query": "AI startups in healthcare",
  "providers": ["perplexity", "linkup"],
  "routing_hints": "focus on recent developments and market trends"
}
```

The system uses the explicitly specified providers but may adjust other aspects based on the hints.