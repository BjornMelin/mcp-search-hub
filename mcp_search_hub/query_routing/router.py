"""Query router for selecting appropriate search providers."""

from typing import List, Dict, Any
from ..models.query import QueryFeatures, SearchQuery
from ..providers.base import SearchProvider
from .cost_optimizer import CostOptimizer


class QueryRouter:
    """Routes queries to appropriate search providers."""
    
    def __init__(self, providers: Dict[str, SearchProvider]):
        self.providers = providers
        self.cost_optimizer = CostOptimizer()
    
    def select_providers(self, query: SearchQuery, features: QueryFeatures, budget: float = None) -> List[str]:
        """Select the best provider(s) for a query based on its features."""
        scores = {}
        
        for name, provider in self.providers.items():
            # Calculate match score
            score = self._calculate_provider_score(name, provider, features)
            scores[name] = score
        
        # If budget is specified, use cost-aware selection
        if budget is not None:
            return self.cost_optimizer.optimize_selection(query, self.providers, scores, budget)
        
        # Otherwise, select based on scores
        ranked_providers = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Take the top provider if its score is significantly better
        if len(ranked_providers) > 1 and ranked_providers[0][1] > ranked_providers[1][1] * 1.25:
            return [ranked_providers[0][0]]
        
        # Otherwise, take the top 2 providers
        return [p[0] for p in ranked_providers[:2]]
    
    def _calculate_provider_score(self, name: str, provider: SearchProvider, features: QueryFeatures) -> float:
        """Calculate how well a provider matches the query features."""
        capabilities = provider.get_capabilities()
        score = 0.0
        
        # Match content type
        if features.content_type in capabilities.get("content_types", []):
            score += 3.0
        
        # Provider-specific scoring
        if name == "linkup":
            # Linkup excels at factual and business queries
            if features.factual_nature > 0.7:
                score += 2.0 * features.factual_nature
            if features.content_type == "business":
                score += 2.0
                
        elif name == "exa":
            # Exa excels at academic content
            if features.content_type == "academic":
                score += 2.5
            # Exa has good semantic search capabilities
            if features.complexity > 0.7:
                score += features.complexity * 1.5
                
        elif name == "perplexity":
            # Perplexity excels at current events and news
            if features.time_sensitivity > 0.7:
                score += 2.0 * features.time_sensitivity
            if features.content_type == "news":
                score += 2.0
                
        elif name == "tavily":
            # Tavily is good for general purpose AI-optimized search
            if features.content_type == "general":
                score += 1.5
            # Good for technical content
            if features.content_type == "technical":
                score += 1.5
                
        elif name == "firecrawl":
            # Firecrawl specializes in web content extraction
            if features.content_type == "web_content":
                score += 3.0
        
        return score