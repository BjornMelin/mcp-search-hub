"""Simple heuristics for analysing queries prior to routing."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..models import QueryIntent, SearchQuery

_KEYWORD_MAP: dict[QueryIntent, Iterable[str]] = {
    QueryIntent.TECHNICAL: ("api", "sdk", "stack trace", "error", "bug", "code"),
    QueryIntent.RESEARCH: ("paper", "study", "dataset", "academic", "research"),
    QueryIntent.NEWS: ("news", "breaking", "headline", "today"),
    QueryIntent.CODE: ("python", "javascript", "function", "class", "snippet"),
}


class QueryClassifier:
    """Basic text heuristics used by the planner to tag queries."""

    def classify_intent(self, query: SearchQuery) -> QueryIntent:
        """Return the most likely intent for the query."""

        normalized = query.query.lower()
        for intent, keywords in _KEYWORD_MAP.items():
            if any(keyword in normalized for keyword in keywords):
                return intent
        return QueryIntent.GENERAL

    def infer_tags(self, query: SearchQuery) -> set[str]:
        """Infer provider tags for the supplied query."""

        inferred = set(query.tags)
        normalized = query.query.lower()

        if re.search(r"\b(cve|exploit|vulnerability)\b", normalized):
            inferred.add("security")
        if re.search(r"\bgithub|gitlab|repository\b", normalized):
            inferred.add("code")
        if any(word in normalized for word in ("paper", "study", "arxiv")):
            inferred.add("research")
        if any(word in normalized for word in ("news", "headline", "update")):
            inferred.add("news")

        intent = self.classify_intent(query)
        inferred.add(intent.value)
        return inferred

    def describe(self, query: SearchQuery) -> dict[str, str | set[str]]:
        """Return a metadata dict summarising classifier output."""

        intent = self.classify_intent(query)
        tags = self.infer_tags(query)
        return {"intent": intent.value, "tags": tags}


__all__ = ["QueryClassifier"]
