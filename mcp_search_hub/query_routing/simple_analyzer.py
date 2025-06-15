"""Simple keyword-based content detector without ML dependencies.

This module provides a lightweight alternative to ML-based content detection,
using keyword patterns and simple heuristics to analyze queries and detect
content types.
"""

from __future__ import annotations

import re
from typing import Literal

ContentType = Literal["news", "technical", "academic", "commercial", "general"]


class SimpleContentDetector:
    """Simple content type detector using keyword patterns.

    This class replaces the ML-based content classifier with a lightweight
    keyword-based approach. It uses predefined keyword patterns to classify
    queries into content types without requiring any ML dependencies.
    """

    def __init__(self) -> None:
        """Initialize the detector with keyword patterns."""
        # Define keyword patterns for each content type
        self.content_patterns = {
            "news": [
                "latest",
                "breaking",
                "today",
                "yesterday",
                "recent",
                "news",
                "update",
                "current",
                "happening",
                "announced",
                "this week",
                "this month",
                "headlines",
                "report",
            ],
            "technical": [
                "api",
                "documentation",
                "tutorial",
                "how to",
                "guide",
                "code",
                "programming",
                "software",
                "library",
                "framework",
                "install",
                "configure",
                "setup",
                "implementation",
                "debug",
                "error",
                "bug",
                "fix",
                "version",
                "release",
                "github",
            ],
            "academic": [
                "research",
                "paper",
                "study",
                "analysis",
                "journal",
                "publication",
                "thesis",
                "dissertation",
                "scholar",
                "peer-reviewed",
                "scientific",
                "academic",
                "theory",
                "methodology",
                "hypothesis",
                "evidence",
                "findings",
            ],
            "commercial": [
                "buy",
                "price",
                "product",
                "review",
                "purchase",
                "shop",
                "store",
                "deal",
                "discount",
                "sale",
                "cost",
                "cheap",
                "expensive",
                "compare prices",
                "best",
                "top rated",
                "customer",
                "shipping",
            ],
        }

    def detect_content_type(self, query: str) -> ContentType:
        """Detect content type based on keyword patterns.

        Args:
            query: The search query to analyze

        Returns:
            The detected content type
        """
        query_lower = query.lower()

        # Count keyword matches for each content type
        scores = {}
        for content_type, keywords in self.content_patterns.items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            scores[content_type] = score

        # Return the content type with the highest score
        if max(scores.values()) > 0:
            return max(scores.items(), key=lambda x: x[1])[0]

        return "general"

    def is_question(self, query: str) -> bool:
        """Check if the query is a question.

        Args:
            query: The search query to analyze

        Returns:
            True if the query appears to be a question
        """
        question_words = [
            "what",
            "who",
            "when",
            "where",
            "why",
            "how",
            "which",
            "can",
            "will",
            "is",
            "are",
            "do",
            "does",
        ]
        query_lower = query.lower()

        # Check for question words at the beginning
        for word in question_words:
            if query_lower.startswith(word + " "):
                return True

        # Check for question mark
        if "?" in query:
            return True

        return False

    def get_query_length_category(
        self, query: str
    ) -> Literal["short", "medium", "long"]:
        """Categorize query length.

        Args:
            query: The search query to analyze

        Returns:
            The length category of the query
        """
        word_count = len(query.split())

        if word_count <= 3:
            return "short"
        if word_count <= 8:
            return "medium"
        return "long"

    def extract_key_entities(self, query: str) -> list[str]:
        """Extract key entities from the query using simple noun extraction.

        This is a simplified version that extracts potential entities without
        using NLP libraries. It looks for capitalized words and common patterns.

        Args:
            query: The search query to analyze

        Returns:
            List of potential key entities
        """
        entities = []

        # Extract capitalized words (potential proper nouns)
        # Skip the first word if it's capitalized due to being at the start
        words = query.split()
        for i, word in enumerate(words):
            # Remove common punctuation
            clean_word = word.strip(".,!?;:")

            # Check if it's capitalized and not at the start or after punctuation
            if (
                clean_word
                and clean_word[0].isupper()
                and (i > 0 or (i == 0 and not query[0].isupper()))
            ):
                entities.append(clean_word)

        # Extract quoted phrases
        quoted_matches = re.findall(r'"([^"]+)"', query)
        entities.extend(quoted_matches)

        # Extract URLs
        url_pattern = r"https?://[^\s]+"
        url_matches = re.findall(url_pattern, query)
        entities.extend(url_matches)

        # Extract common entity patterns
        # Company names ending with Inc., Ltd., etc.
        company_pattern = r"\b\w+\s+(?:Inc|Ltd|LLC|Corp|Corporation)\b"
        company_matches = re.findall(company_pattern, query, re.IGNORECASE)
        entities.extend(company_matches)

        # Years
        year_pattern = r"\b(?:19|20)\d{2}\b"
        year_matches = re.findall(year_pattern, query)
        entities.extend(year_matches)

        # Remove duplicates while preserving order
        seen = set()
        unique_entities = []
        for entity in entities:
            if entity.lower() not in seen:
                seen.add(entity.lower())
                unique_entities.append(entity)

        return unique_entities
