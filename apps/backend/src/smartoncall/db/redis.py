import redis.asyncio as aioredis

from smartoncall.config import get_settings

settings = get_settings()

redis_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    global redis_client
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return redis_client


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.aclose()
        redis_client = None


def get_redis() -> aioredis.Redis:
    if redis_client is None:
        raise RuntimeError("Redis 未初始化，请先调用 init_redis()")
    return redis_client
