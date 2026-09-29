# 提供 FastAPI 缓存客户端依赖。

from redis.asyncio import Redis

from app.cache.client import get_redis_client


async def get_cache() -> Redis:
    return get_redis_client()
