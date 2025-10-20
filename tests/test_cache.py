"""Tests for the hybrid search cache."""

from __future__ import annotations

import asyncio

from mcp_search_hub.cache import SearchCache
from mcp_search_hub.models import CombinedSearchResponse, SearchQuery


async def _round_trip(cache: SearchCache) -> bool:
    query = SearchQuery(query="alpha", max_results=5)
    cached = await cache.get(query)
    assert cached is None

    response = CombinedSearchResponse(results=[], providers=[], metadata={"echo": True})
    await cache.set(query, response)
    restored = await cache.get(query)
    assert restored is not None
    assert restored.metadata == {"echo": True}
    return True


def test_cache_round_trip():
    cache = SearchCache(
        memory_ttl=5,
        redis_enabled=False,
        redis_url=None,
        redis_ttl=30,
        prefix="search",
        ttl_jitter=0,
    )
    assert asyncio.run(_round_trip(cache))


def test_fingerprint_stable():
    query = SearchQuery(query="same", max_results=5, advanced={"foo": "bar"})
    fp1 = SearchCache.fingerprint(query)
    fp2 = SearchCache.fingerprint(query)
    assert fp1 == fp2
