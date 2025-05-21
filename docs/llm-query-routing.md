# LLM-Directed Query Routing

This document outlines approaches for allowing client LLMs to influence or control query routing decisions in MCP Search Hub.

## 1. Explicit Routing Parameters

The simplest approach is to extend the MCP tool schemas to include optional routing parameters.

### Implementation

Add routing parameters to the search tools:

```python
class SearchParameters(BaseModel):
    query: str
    providers: list[str] | None = None  # ["tavily", "perplexity", etc.]
    strategy: str | None = None  # "parallel", "cascade", "best_match"
    max_providers: int | None = None  # Limit number of providers used
    budget: Decimal | None = None  # Maximum budget to use for this query
    require_all_results: bool | None = None  # Wait for all providers or return fastest
```

This approach gives LLMs direct control over routing decisions while maintaining backward compatibility with clients that don't specify these parameters.

## 2. Intent-Based Routing

A more sophisticated approach that leverages the LLM's reasoning abilities without requiring explicit routing parameters.

### Implementation

1. Create an `IntentAnalyzer` that extracts search intent from queries:

```python
class IntentAnalyzer:
    """Analyzes search intent from query text."""
    
    def analyze(self, query: str) -> dict[str, Any]:
        """Extract search intent features from query text.
        
        Returns:
            Dictionary with intent features:
            - requires_recent: Whether query needs very recent information
            - domain_specific: Domain-specific areas ("academic", "news", etc.)
            - depth_required: Depth of information needed ("basic", "detailed", "comprehensive")
            - geographic_focus: Geographic regions mentioned
            - time_sensitive: Whether query is time-sensitive
        """
        # Implementation using ML models or rule-based approach
```

2. Update the `UnifiedRouter` to consider these intent features:

```python
class UnifiedRouter:
    def select_providers(self, query: str, intent: dict[str, Any]) -> list[Provider]:
        """Select providers based on query and extracted intent."""
        # Use intent features to refine provider selection
```

3. Add a pre-processing step to the server to extract intent before routing.

This approach allows LLMs to influence routing implicitly through how they formulate their queries, without changing the API contract.

## 3. Hybrid Approach: Provider Hints

A middle ground that allows for flexible routing hints without rigid parameters.

### Implementation

Extend the search parameters to include an optional "hints" field:

```python
class SearchParameters(BaseModel):
    query: str
    routing_hints: str | None = None  # Free-form routing guidance
```

The `routing_hints` field could contain natural language instructions like:
- "Prioritize academic sources for this research question"
- "Need very recent news on this topic"
- "Focus on high-quality images for this search"

A `RoutingHintParser` component would process these hints and adjust the routing strategy accordingly.

## Implementation Considerations

1. **Performance Impact**: Both approaches add minimal overhead to query processing.
2. **Backward Compatibility**: All approaches maintain backward compatibility with existing clients.
3. **Security**: Input validation is essential for explicitly provided routing parameters.
4. **Defaults**: Conservative defaults ensure reasonable performance when routing guidance is absent.
5. **Observability**: Log how routing decisions are influenced by client input for debugging and improvement.

## Recommended Path Forward

The hybrid approach offers the best balance of flexibility and simplicity:

1. Implement explicit routing parameters for direct control
2. Add support for natural language routing hints
3. Improve intent extraction over time based on usage patterns

This gives LLM clients multiple ways to influence routing decisions based on their capabilities and needs, while maintaining a clean API surface.