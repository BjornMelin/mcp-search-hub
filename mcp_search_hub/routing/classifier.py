"""Small deterministic query tag inference."""

from __future__ import annotations

import re

from ..models import SearchQuery

_TAG_PATTERNS = {
    "code": re.compile(r"\b(api|code|function|github|gitlab|python|javascript|sdk)\b"),
    "news": re.compile(r"\b(breaking|headline|latest|news|today|update)\b"),
    "research": re.compile(r"\b(academic|arxiv|dataset|paper|research|study)\b"),
    "security": re.compile(r"\b(cve|exploit|security|vulnerability)\b"),
    "technical": re.compile(r"\b(bug|error|stack trace|technical)\b"),
}


def infer_tags(query: SearchQuery) -> set[str]:
    """Combine explicit tags with predictable keyword matches."""

    tags = set(query.tags)
    normalized = query.query.casefold()
    tags.update(tag for tag, pattern in _TAG_PATTERNS.items() if pattern.search(normalized))
    if not tags:
        tags.add("general")
    return tags


__all__ = ["infer_tags"]
