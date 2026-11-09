import os
import logging
import redis.asyncio as redis

logger = logging.getLogger("lbvd.redis")

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0"
)

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    health_check_interval=30,
    max_connections=50,
)


async def check_redis():
    try:
        result = await redis_client.ping()
        return result
    except redis.RedisError:
        logger.exception("Redis health check failed")
        raise


async def close_redis():
    await redis_client.aclose()
    logger.info("Redis connection closed")