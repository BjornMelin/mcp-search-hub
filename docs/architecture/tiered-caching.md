# Tiered Caching System

MCP Search Hub features a sophisticated tiered caching system that combines in-memory and Redis-backed distributed caching to optimize performance, reduce API costs, and improve scalability.

## Caching Architecture

The caching system uses a two-tier approach:

1. **Memory Cache (First Tier)**
   - Fast, in-process memory cache
   - Short TTL (Time-To-Live) for hot, recent queries
   - Zero network overhead
   - Process-local (not shared between instances)

2. **Redis Cache (Second Tier)**
   - Distributed, persistent cache
   - Longer TTL for frequently accessed queries
   - Shared between all server instances
   - Survives process restarts

## Key Features

### Semantic Query Fingerprinting

The caching system includes intelligent query fingerprinting that allows semantically similar queries to hit the same cache entry:

- Normalizes query parameters
- Removes request-specific identifiers and timestamps
- Generates consistent cache keys for equivalent queries
- Configurable via `CACHE_FINGERPRINT_ENABLED`

### Tiered Cache Strategy

When a query is received:

1. First check memory cache (fastest)
2. If not found, check Redis cache (distributed)
3. If still not found, execute query and cache the result in both tiers

### Cache Invalidation

The system supports multiple invalidation strategies:

- **Time-based invalidation**
  - Memory cache: Short TTL (default: 5 minutes)
  - Redis cache: Longer TTL (default: 1 hour)

- **Explicit key invalidation**
  - Clear specific cache keys
  - Clear keys matching a pattern
  - Clear all cache

### Fallback Behavior

The system is designed to be resilient:

- If Redis is unavailable, falls back to memory cache
- If memory cache item is expired, checks Redis before fetching fresh data
- Graceful handling of serialization/deserialization errors

## Configuration

Configure the caching system through environment variables:

```bash
# Basic cache configuration
CACHE_TTL=300                    # Legacy memory-only cache TTL in seconds (for backward compatibility)
CACHE_MEMORY_TTL=300             # Memory cache TTL for tiered cache (5 minutes)
CACHE_REDIS_TTL=3600             # Redis cache TTL for tiered cache (1 hour)

# Redis configuration
REDIS_URL=redis://localhost:6379  # Redis connection URL (host, port, password, etc.)
REDIS_CACHE_ENABLED=false         # Set to 'true' to enable Redis caching

# Advanced settings
CACHE_PREFIX=search:              # Prefix for Redis cache keys
CACHE_FINGERPRINT_ENABLED=true    # Enable semantic fingerprinting for queries
CACHE_CLEAN_INTERVAL=600          # Cache cleanup interval (10 minutes)
```

## Implementation Details

The caching system is implemented in `mcp_search_hub/utils/cache.py` with two main classes:

1. `QueryCache`: Legacy memory-only cache (for backward compatibility)
2. `TieredCache`: New tiered cache implementation with Redis support

```python
# Example usage in the SearchServer class
if self.settings.cache.redis_enabled:
    # Use tiered cache with Redis
    self.cache = TieredCache(
        redis_url=self.settings.cache.redis_url,
        memory_ttl=self.settings.cache.memory_ttl,
        redis_ttl=self.settings.cache.redis_ttl,
        prefix=self.settings.cache.prefix,
        fingerprint_enabled=self.settings.cache.fingerprint_enabled,
    )
else:
    # Use legacy memory-only cache
    self.cache = QueryCache(ttl=self.settings.cache_ttl)
```

## Benefits

- **Improved Performance**: Responses served from cache are typically 100x faster
- **Reduced API Costs**: Lower provider API usage by caching common queries
- **Scalability**: Redis-backed caching allows multiple instances to share cache
- **Resilience**: Fallback to memory cache when Redis is unavailable
- **Flexibility**: Different TTLs for different cache tiers optimize memory usage

## Best Practices

1. **Select appropriate TTLs** based on query freshness requirements:
   - Short TTLs for rapidly changing data
   - Longer TTLs for stable informational queries

2. **Enable fingerprinting** for improved cache hit rates on similar queries

3. **Use Redis caching** in multi-instance deployments for shared cache

4. **Adjust memory cache size** based on server RAM limitations

5. **Monitor cache performance** using metrics endpoint