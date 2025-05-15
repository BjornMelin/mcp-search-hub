"""Query analyzer for extracting features."""

from typing import Dict, Any, List
import re
from ..models.query import SearchQuery, QueryFeatures


class QueryAnalyzer:
    """Analyzes search queries to extract features for routing."""
    
    def extract_features(self, query: SearchQuery) -> QueryFeatures:
        """Extract features from a search query."""
        text = query.query
        
        # Basic features
        features = {
            "length": len(text),
            "word_count": len(text.split()),
            "contains_question": any(q in text.lower() for q in ["what", "how", "why", "when", "who", "where"]),
        }
        
        # Content type detection
        content_type = query.content_type or self._detect_content_type(text)
        features["content_type"] = content_type
        
        # Time sensitivity
        features["time_sensitivity"] = self._calculate_time_sensitivity(text)
        
        # Complexity
        features["complexity"] = self._calculate_complexity(text)
        
        # Factual nature
        features["factual_nature"] = self._calculate_factual_nature(text)
        
        return QueryFeatures(**features)
    
    def _detect_content_type(self, text: str) -> str:
        """Detect the type of content the query is seeking."""
        text_lower = text.lower()
        
        # Academic/research indicators
        academic_indicators = ["research", "paper", "study", "journal", "publication", "thesis", "dissertation", "scholar"]
        if any(indicator in text_lower for indicator in academic_indicators):
            return "academic"
        
        # News/current events indicators
        news_indicators = ["news", "latest", "recent", "update", "today", "yesterday", "this week", "this month", "current"]
        if any(indicator in text_lower for indicator in news_indicators):
            return "news"
        
        # Technical indicators
        technical_indicators = ["code", "program", "library", "framework", "documentation", "api", "software", "development"]
        if any(indicator in text_lower for indicator in technical_indicators):
            return "technical"
        
        # Business/corporate indicators
        business_indicators = ["company", "business", "corporate", "industry", "market", "product", "service", "linkedin"]
        if any(indicator in text_lower for indicator in business_indicators):
            return "business"
        
        # Web content indicators
        web_indicators = ["website", "webpage", "url", "extract", "scrape", "content"]
        if any(indicator in text_lower for indicator in web_indicators):
            return "web_content"
        
        # Default to general
        return "general"
    
    def _calculate_time_sensitivity(self, text: str) -> float:
        """Calculate the time sensitivity score (0.0 to 1.0)."""
        text_lower = text.lower()
        
        # High time sensitivity indicators
        high_indicators = ["latest", "just now", "breaking", "today", "current", "live"]
        if any(indicator in text_lower for indicator in high_indicators):
            return 1.0
        
        # Medium time sensitivity indicators
        medium_indicators = ["recent", "this week", "new", "update"]
        if any(indicator in text_lower for indicator in medium_indicators):
            return 0.7
        
        # Low time sensitivity indicators
        low_indicators = ["this year", "this month", "modern"]
        if any(indicator in text_lower for indicator in low_indicators):
            return 0.4
        
        # Default: moderate time sensitivity
        return 0.3
    
    def _calculate_complexity(self, text: str) -> float:
        """Calculate the query complexity score (0.0 to 1.0)."""
        # Length-based complexity
        length_score = min(len(text) / 100, 1.0) * 0.5
        
        # Advanced query indicators
        advanced_patterns = [
            r"compare .+ and", r"relationship between", r"difference between",
            r"pros and cons", r"advantages .+ disadvantages", r"implications of",
            r"explain .+ with examples", r"analyze"
        ]
        
        pattern_matches = any(re.search(pattern, text.lower()) for pattern in advanced_patterns)
        pattern_score = 0.5 if pattern_matches else 0.0
        
        return length_score + pattern_score
    
    def _calculate_factual_nature(self, text: str) -> float:
        """Calculate the factual nature score (0.0 to 1.0)."""
        text_lower = text.lower()
        
        # Highly factual indicators
        factual_indicators = ["how many", "when did", "who is", "where is", "what is the", "how much", "statistics"]
        if any(indicator in text_lower for indicator in factual_indicators):
            return 0.9
        
        # Opinion-seeking indicators
        opinion_indicators = ["why is", "opinion", "perspective", "viewpoint", "debate", "controversial"]
        if any(indicator in text_lower for indicator in opinion_indicators):
            return 0.2
        
        # Default: moderate factual nature
        return 0.5