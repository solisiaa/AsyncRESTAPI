"""Redis caching helpers: key builders + get/set/invalidate."""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any, Callable, Coroutine, Dict, Optional, TypeVar

if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:  # Python 3.9 fallback (local test env); 3.11+ uses typing.ParamSpec.
    from typing_extensions import ParamSpec

import redis.asyncio as redis_async

from app.core.redis import get_redis_client

P = ParamSpec("P")
R = TypeVar("R")


def project_key(project_id: int) -> str:
    """Build cache key for a single project."""
    return f"project:{project_id}"


def projects_list_key(params_hash: str) -> str:
    """Build cache key for a projects list query."""
    return f"projects:list:{params_hash}"


def top_assignees_key(params_hash: str) -> str:
    """Build cache key for top-assignees analytics."""
    return f"analytics:top_assignees:{params_hash}"


def hash_params(params: Dict[str, Any]) -> str:
    """Stable short hash of query params dict."""
    raw = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def cache_get(client: redis_async.Redis, key: str) -> Optional[str]:
    """Get a cached string value or None."""
    value: Optional[str] = await client.get(key)
    return value


async def cache_set(client: redis_async.Redis, key: str, value: str, ttl: int) -> None:
    """Set a cached string value with TTL (seconds)."""
    await client.set(key, value, ex=ttl)


async def invalidate_pattern(client: redis_async.Redis, pattern: str) -> int:
    """Delete all keys matching a pattern. Returns number of deleted keys."""
    deleted = 0
    try:
        async for key in client.scan_iter(match=pattern):
            # key is str because decode_responses=True
            await client.delete(key)
            deleted += 1
    except Exception:
        return deleted
    return deleted


async def invalidate_project_cache(project_id: int) -> None:
    """Invalidate single-project and projects-list caches."""
    try:
        client = get_redis_client()
        await client.delete(project_key(project_id))
        await invalidate_pattern(client, "projects:list:*")
    except Exception:
        pass


async def invalidate_analytics_cache() -> None:
    """Invalidate analytics caches (called on task mutations)."""
    try:
        client = get_redis_client()
        await invalidate_pattern(client, "analytics:*")
    except Exception:
        pass


def cache(
    ttl: int,
    key_builder: Callable[..., str],
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    """Decorator for caching async function results in Redis as JSON.

    The decorated function must return JSON-serializable data.
    Cache misses call the wrapped function and store its result.

    Args:
        ttl: Time-to-live in seconds.
        key_builder: Function building a cache key from call args/kwargs.

    Returns:
        Decorator for async functions.
    """

    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key = key_builder(*args, **kwargs)
            client = get_redis_client()
            try:
                cached = await client.get(key)
            except Exception:
                cached = None
            if cached is not None:
                data = json.loads(cached)
                return data  # type: ignore[no-any-return]
            result = await func(*args, **kwargs)
            try:
                await client.set(key, json.dumps(result, default=str), ex=ttl)
            except Exception:
                pass
            return result

        return wrapper

    return decorator
