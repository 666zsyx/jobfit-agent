# 创建和释放全局 Redis 异步客户端。

from redis.asyncio import Redis

from app.core.config import settings


redis_client = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
)


def get_redis_client() -> Redis:
    return redis_client


async def dispose_redis() -> None:
    await redis_client.aclose()
