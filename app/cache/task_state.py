# 提供任务状态短期缓存和运行互斥锁。

import json
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)
from redis.asyncio import Redis


TASK_STATUS_TTL_SECONDS = 300
RUN_LOCK_TTL_SECONDS = 120


class CachedTaskStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: int = Field(gt=0)
    status: Literal[
        "pending",
        "running",
        "waiting_confirmation",
        "interrupted",
        "completed",
        "failed",
        "cancelled",
    ]
    current_step: int = Field(ge=0)
    attempt: int = Field(ge=0)
    max_steps: int = Field(gt=0)
    current_node: str | None = None

    @model_validator(mode="after")
    def validate_step_limit(self):
        if self.current_step > self.max_steps:
            raise ValueError("current_step 不能超过 max_steps")
        return self


def _task_status_key(user_id: int, task_id: int) -> str:
    return f"jobfit:user:{user_id}:task:{task_id}:status"


def _task_run_lock_key(task_id: int) -> str:
    return f"jobfit:task:{task_id}:run_lock"


async def cache_task_status(
    redis: Redis,
    *,
    user_id: int,
    task_id: int,
    status: str,
    current_step: int,
    attempt: int,
    max_steps: int,
    current_node: str | None = None,
    ttl: int = TASK_STATUS_TTL_SECONDS,
) -> None:
    if ttl <= 0:
        raise ValueError("ttl 必须大于 0")

    if current_step < 0:
        raise ValueError("current_step 不能小于 0")

    if attempt < 0:
        raise ValueError("attempt 不能小于 0")

    if max_steps <= 0:
        raise ValueError("max_steps 必须大于 0")

    payload = json.dumps(
        {
            "task_id": task_id,
            "status": status,
            "current_step": current_step,
            "attempt": attempt,
            "max_steps": max_steps,
            "current_node": current_node,
        },
        ensure_ascii=False,
    )
    await redis.set(
        _task_status_key(user_id, task_id),
        payload,
        ex=ttl,
    )


async def get_cached_task_status(
    redis: Redis,
    *,
    user_id: int,
    task_id: int,
) -> dict | None:
    key = _task_status_key(user_id, task_id)
    raw_value = await redis.get(key)

    if raw_value is None:
        return None

    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8")

    try:
        value = json.loads(raw_value)
    except (TypeError, ValueError):
        await redis.delete(key)
        return None

    try:
        validated = CachedTaskStatus.model_validate(value)
    except ValidationError:
        await redis.delete(key)
        return None

    return validated.model_dump()


async def invalidate_task_status(
    redis: Redis,
    *,
    user_id: int,
    task_id: int,
) -> None:
    await redis.delete(_task_status_key(user_id, task_id))


async def acquire_task_run_lock(
    redis: Redis,
    *,
    task_id: int,
    owner_token: str,
    ttl: int = RUN_LOCK_TTL_SECONDS,
) -> bool:
    if not owner_token.strip():
        raise ValueError("owner_token 不能为空")

    if ttl <= 0:
        raise ValueError("ttl 必须大于 0")

    result = await redis.set(
        _task_run_lock_key(task_id),
        owner_token,
        nx=True,
        ex=ttl,
    )
    return bool(result)


_RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


async def release_task_run_lock(
    redis: Redis,
    *,
    task_id: int,
    owner_token: str,
) -> bool:
    if not owner_token.strip():
        raise ValueError("owner_token 不能为空")

    result = await redis.eval(
        _RELEASE_LOCK_LUA,
        1,
        _task_run_lock_key(task_id),
        owner_token,
    )
    return int(result) == 1
