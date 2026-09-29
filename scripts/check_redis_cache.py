# 验证真实 Redis 的任务状态缓存。

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.cache.client import get_redis_client
from app.cache.task_state import (
    cache_task_status,
    get_cached_task_status,
    invalidate_task_status,
)


async def check_redis_cache() -> None:
    redis = get_redis_client()
    suffix = uuid4().int
    user_id = 1_000_000 + suffix % 1_000_000
    other_user_id = user_id + 1
    task_id = 2_000_000 + suffix % 1_000_000
    key = f"jobfit:user:{user_id}:task:{task_id}:status"

    try:
        assert await redis.ping() is True
        print("redis_ping_ok")

        await cache_task_status(
            redis,
            user_id=user_id,
            task_id=task_id,
            status="running",
            current_step=2,
            attempt=1,
            max_steps=8,
        )
        cached = await get_cached_task_status(
            redis,
            user_id=user_id,
            task_id=task_id,
        )
        assert cached == {
            "task_id": task_id,
            "status": "running",
            "current_step": 2,
            "attempt": 1,
            "max_steps": 8,
        }
        print("cache_set_get_ok")

        ttl = await redis.ttl(key)
        assert 1 <= ttl <= 300
        print("cache_ttl_ok")

        other_value = await get_cached_task_status(
            redis,
            user_id=other_user_id,
            task_id=task_id,
        )
        assert other_value is None
        print("cache_user_namespace_ok")

        await invalidate_task_status(
            redis,
            user_id=user_id,
            task_id=task_id,
        )
        assert await get_cached_task_status(
            redis,
            user_id=user_id,
            task_id=task_id,
        ) is None
        print("cache_invalidate_ok")

        await redis.set(key, "{bad-json")
        assert await get_cached_task_status(
            redis,
            user_id=user_id,
            task_id=task_id,
        ) is None
        assert await redis.exists(key) == 0
        print("corrupted_cache_cleanup_ok")
        print("redis_cache_check_ok")
    finally:
        await redis.delete(key)
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(check_redis_cache())
