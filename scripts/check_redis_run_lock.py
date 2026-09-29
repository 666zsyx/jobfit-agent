# 验证真实 Redis 的任务运行锁。

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.cache.client import get_redis_client
from app.cache.task_state import (
    acquire_task_run_lock,
    release_task_run_lock,
)


async def check_redis_run_lock() -> None:
    redis = get_redis_client()
    task_id = 3_000_000 + uuid4().int % 1_000_000
    owner = f"owner-{uuid4().hex}"
    wrong_owner = f"wrong-{uuid4().hex}"
    key = f"jobfit:task:{task_id}:run_lock"

    try:
        assert await acquire_task_run_lock(
            redis,
            task_id=task_id,
            owner_token=owner,
        ) is True
        print("redis_lock_acquire_ok")

        assert await acquire_task_run_lock(
            redis,
            task_id=task_id,
            owner_token="other-owner",
        ) is False
        print("redis_lock_conflict_ok")

        assert await release_task_run_lock(
            redis,
            task_id=task_id,
            owner_token=wrong_owner,
        ) is False
        print("redis_lock_wrong_owner_rejected")

        ttl = await redis.ttl(key)
        assert 1 <= ttl <= 120
        print("redis_lock_ttl_ok")

        assert await release_task_run_lock(
            redis,
            task_id=task_id,
            owner_token=owner,
        ) is True
        print("redis_lock_release_ok")
        print("redis_run_lock_check_ok")
    finally:
        await redis.delete(key)
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(check_redis_run_lock())
