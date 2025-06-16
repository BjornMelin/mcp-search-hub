"""Query complexity classifier for routing decisions.

This module provides a lightweight complexity scoring system to determine
which routing tier should handle a query. It uses simple heuristics without
ML dependencies for fast, deterministic classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ..models.query import SearchQuery

ComplexityLevel = Literal["simple", "medium", "complex"]


@dataclass
class ComplexityScore:
    """Result of complexity analysis."""

    score: float  # 0.0 (simple) to 1.0 (complex)
    level: ComplexityLevel
    factors: dict[str, float]  # Individual factor contributions
    explanation: str


class ComplexityClassifier:
    """Classifies query complexity for routing decisions.

    This classifier uses multiple factors to determine query complexity:
    - Query length and structure
    - Presence of multiple intents
    - Technical or specialized vocabulary
    - Ambiguity indicators
    - Cross-domain references
    """

    # Complexity thresholds
    SIMPLE_THRESHOLD = 0.3
    MEDIUM_THRESHOLD = 0.7

    def __init__(self):
        """Initialize the complexity classifier."""
        # Keywords indicating complex queries
        self.complex_keywords = {
            "compare",
            "analyze",
            "evaluate",
            "assess",
            "explain",
            "relationship",
            "impact",
            "effect",
            "influence",
            "considering",
            "versus",
            "vs",
            "between",
            "among",
            "trade-off",
            "pros and cons",
            "comprehensive",
            "detailed",
            "in-depth",
            "thorough",
        }

        # Domain crossing indicators
        self.cross_domain_patterns = [
            r"(\w+)\s+and\s+(\w+)\s+(?:impact|effect|influence)",
            r"(?:environmental|economic|social)\s+(?:impact|implications)",
            r"(?:historical|future)\s+(?:context|perspective)",
        ]

        # Ambiguity indicators
        self.ambiguity_words = {
            "might",
            "could",
            "possibly",
            "perhaps",
            "maybe",
            "sometimes",
            "generally",
            "usually",
            "often",
            "various",
        }

    def classify(self, query: SearchQuery) -> ComplexityScore:
        """Classify the complexity of a search query.

        Args:
            query: The search query to analyze

        Returns:
            ComplexityScore with detailed analysis
        """
        query_text = query.query.lower()
        factors = {}

        # Factor 1: Query length (0.0 - 0.25)
        word_count = len(query_text.split())
        if word_count <= 3:
            factors["length"] = 0.0
        elif word_count <= 6:
            factors["length"] = 0.1
        elif word_count <= 10:
            factors["length"] = 0.15
        elif word_count <= 15:
            factors["length"] = 0.2
        else:
            factors["length"] = 0.25

        # Factor 2: Complex keywords (0.0 - 0.4)
        complex_keyword_count = sum(
            1 for keyword in self.complex_keywords if keyword in query_text
        )
        factors["complex_keywords"] = min(complex_keyword_count * 0.15, 0.4)

        # Factor 3: Question complexity (0.0 - 0.2)
        if self._is_how_why_question(query_text):
            factors["question_type"] = 0.2
        elif "?" in query_text or any(
            q in query_text for q in ["what", "how", "why", "when", "where"]
        ):
            factors["question_type"] = 0.1
        else:
            factors["question_type"] = 0.0

        # Factor 4: Multiple intents (0.0 - 0.2)
        intent_count = self._count_intents(query_text)
        if intent_count >= 3:
            factors["multi_intent"] = 0.2
        elif intent_count == 2:
            factors["multi_intent"] = 0.1
        else:
            factors["multi_intent"] = 0.0

        # Factor 5: Cross-domain indicators (0.0 - 0.2)
        if self._has_cross_domain_indicators(query_text):
            factors["cross_domain"] = 0.2
        else:
            factors["cross_domain"] = 0.0

        # Factor 6: Ambiguity (0.0 - 0.1)
        ambiguity_count = sum(1 for word in self.ambiguity_words if word in query_text)
        factors["ambiguity"] = min(ambiguity_count * 0.05, 0.1)

        # Calculate total score
        total_score = sum(factors.values())
        total_score = min(total_score, 1.0)  # Cap at 1.0

        # Determine level
        if total_score < self.SIMPLE_THRESHOLD:
            level = "simple"
            explanation = "Query is straightforward with clear intent"
        elif total_score < self.MEDIUM_THRESHOLD:
            level = "medium"
            explanation = "Query has moderate complexity requiring pattern analysis"
        else:
            level = "complex"
            explanation = (
                "Query is complex with multiple factors requiring deep analysis"
            )

        # Add specific factor explanations
        if factors["complex_keywords"] > 0.1:
            explanation += ". Contains analytical keywords"
        if factors["multi_intent"] > 0.1:
            explanation += ". Multiple intents detected"
        if factors["cross_domain"] > 0:
            explanation += ". Crosses multiple domains"

        return ComplexityScore(
            score=total_score, level=level, factors=factors, explanation=explanation
        )

    def _is_how_why_question(self, query: str) -> bool:
        """Check if query is a complex how/why question."""
        return bool(re.match(r"^(how|why|explain)\s+", query))

    def _count_intents(self, query: str) -> int:
        """Count the number of distinct intents in the query."""
        # Simple heuristic: count conjunctions and commas
        intent_markers = ["and", ",", "also", "plus", "as well as", "including"]
        count = 1  # Start with 1 for the base intent

        for marker in intent_markers:
            count += query.count(marker)

        # Check for listed items
        if re.search(r"\d+\.", query) or re.search(r"[a-z]\)", query):
            count += 2  # Lists indicate multiple intents

        return count

    def _has_cross_domain_indicators(self, query: str) -> bool:
        """Check if query spans multiple domains."""
        for pattern in self.cross_domain_patterns:
            if re.search(pattern, query):
                return True

        # Check for multiple domain keywords
        domains = [
            "environmental",
            "economic",
            "social",
            "technical",
            "political",
            "cultural",
            "historical",
            "scientific",
        ]
        domain_count = sum(1 for domain in domains if domain in query)

        return domain_count >= 2
