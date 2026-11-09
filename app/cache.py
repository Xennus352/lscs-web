import json
import logging
from typing import Any

from redis.exceptions import RedisError

from app.redis_client import redis_client

logger = logging.getLogger("lbvd.cache")


async def get_cache(key: str) -> Any | None:
    """Get JSON data from Redis. Return None if missing or unavailable."""
    try:
        value = await redis_client.get(key)

        if value is None:
            return None

        return json.loads(value)

    except (RedisError, json.JSONDecodeError):
        logger.warning("Redis cache read failed: %s", key, exc_info=True)
        return None


async def set_cache(
    key: str,
    value: Any,
    ttl: int = 300,
) -> bool:
    """Store JSON data in Redis with an expiration time."""
    try:
        if ttl <= 0:
            raise ValueError("Cache TTL must be greater than zero")

        serialized = json.dumps(
            value,
            ensure_ascii=False,
            default=str,
        )

        await redis_client.set(
            key,
            serialized,
            ex=ttl,
        )

        return True

    except RedisError:
        logger.warning("Redis cache write failed: %s", key, exc_info=True)
        return False


async def delete_cache(key: str) -> bool:
    """Delete one cache key from Redis."""
    try:
        await redis_client.delete(key)
        return True

    except RedisError:
        logger.warning("Redis cache delete failed: %s", key, exc_info=True)
        return False
