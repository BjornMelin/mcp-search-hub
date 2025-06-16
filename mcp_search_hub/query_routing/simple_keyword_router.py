"""Simple keyword-based router for Tier 1 routing.

This module provides ultra-fast routing based on keywords, domains, and
simple patterns. It handles 80% of queries with <1ms latency.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from ..models.query import SearchQuery
from ..providers.base import SearchProvider


class SimpleKeywordRouter:
    """Fast keyword-based router for simple queries.

    This router uses keyword patterns and domain detection to route
    queries to appropriate providers with minimal latency.
    """

    def __init__(self, providers: dict[str, SearchProvider]):
        """Initialize the keyword router.

        Args:
            providers: Available search providers
        """
        self.providers = providers

        # Provider-specific keyword patterns
        self.provider_keywords = {
            "linkup": {
                "keywords": [
                    "latest",
                    "today",
                    "yesterday",
                    "recent",
                    "news",
                    "current",
                    "breaking",
                    "update",
                    "happening",
                ],
                "priority": 1.0,
            },
            "exa": {
                "keywords": [
                    "research",
                    "paper",
                    "study",
                    "academic",
                    "scholar",
                    "journal",
                    "publication",
                    "thesis",
                    "scientific",
                ],
                "priority": 0.95,
            },
            "tavily": {
                "keywords": [
                    "fact",
                    "information",
                    "data",
                    "statistics",
                    "definition",
                    "what is",
                    "explain",
                    "overview",
                ],
                "priority": 0.9,
            },
            "perplexity": {
                "keywords": [
                    "comprehensive",
                    "detailed",
                    "analysis",
                    "compare",
                    "understand",
                    "deep dive",
                    "thorough",
                    "complete",
                ],
                "priority": 0.85,
            },
            "firecrawl": {
                "keywords": [
                    "website",
                    "page",
                    "content",
                    "extract",
                    "scrape",
                    "article",
                    "blog",
                    "documentation",
                ],
                "domains": ["github.com", "stackoverflow.com", "medium.com"],
                "priority": 0.8,
            },
        }

        # Time-sensitive patterns
        self.time_patterns = [
            r"\b(today|yesterday|this week|this month|last \w+)\b",
            r"\b(latest|recent|current|breaking)\b",
            r"\b\d{4}\b",  # Years
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
        ]

        # Domain patterns for direct routing
        self.domain_routing = {
            "github.com": ["firecrawl", "exa"],
            "arxiv.org": ["exa", "perplexity"],
            "wikipedia.org": ["tavily", "perplexity"],
            "linkedin.com": ["exa"],
            "twitter.com": ["linkup", "tavily"],
            "x.com": ["linkup", "tavily"],
        }

    async def route(self, query: SearchQuery) -> list[str]:
        """Route query based on keywords and patterns.

        Args:
            query: The search query

        Returns:
            List of selected provider names
        """
        query_lower = query.query.lower()
        scores = {}

        # Check for URLs in query
        urls = self._extract_urls(query.query)
        if urls:
            return self._route_by_domain(urls)

        # Check for time-sensitive queries
        if self._is_time_sensitive(query_lower):
            scores["linkup"] = 2.0  # Boost for real-time
            scores["tavily"] = 1.5

        # Score providers based on keyword matches
        for provider, config in self.provider_keywords.items():
            if provider not in self.providers:
                continue

            score = 0.0
            keywords = config.get("keywords", [])

            # Count keyword matches
            matches = sum(1 for keyword in keywords if keyword in query_lower)
            if matches > 0:
                score = matches * config["priority"]

            if score > 0:
                scores[provider] = scores.get(provider, 0) + score

        # If no matches, use default providers
        if not scores:
            return self._get_default_providers()

        # Sort by score and return top providers
        sorted_providers = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Return top 3 providers or all with score > 1.0
        selected = []
        for provider, score in sorted_providers:
            if score > 1.0 or len(selected) < 3:
                selected.append(provider)
            if len(selected) >= 5:  # Max 5 providers
                break

        return selected

    def _extract_urls(self, text: str) -> list[str]:
        """Extract URLs from query text."""
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        return re.findall(url_pattern, text)

    def _route_by_domain(self, urls: list[str]) -> list[str]:
        """Route based on domain in URLs."""
        providers = []

        for url in urls:
            try:
                domain = urlparse(url).netloc.lower()
                # Check exact domain match
                if domain in self.domain_routing:
                    providers.extend(self.domain_routing[domain])
                # Check domain patterns
                else:
                    for (
                        pattern_domain,
                        pattern_providers,
                    ) in self.domain_routing.items():
                        if pattern_domain in domain:
                            providers.extend(pattern_providers)
            except Exception:
                continue

        # Remove duplicates while preserving order
        seen = set()
        unique_providers = []
        for p in providers:
            if p not in seen and p in self.providers:
                seen.add(p)
                unique_providers.append(p)

        return unique_providers or self._get_default_providers()

    def _is_time_sensitive(self, query: str) -> bool:
        """Check if query is time-sensitive."""
        for pattern in self.time_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return True
        return False

    def _get_default_providers(self) -> list[str]:
        """Get default providers when no specific matches."""
        defaults = ["tavily", "linkup", "perplexity"]
        return [p for p in defaults if p in self.providers]
