# 使用 fakeredis 验证任务状态缓存。

import asyncio
import json

import pytest
from fakeredis.aioredis import FakeRedis

from app.cache.task_state import (
    RUN_LOCK_TTL_SECONDS,
    TASK_STATUS_TTL_SECONDS,
    acquire_task_run_lock,
    cache_task_status,
    get_cached_task_status,
    invalidate_task_status,
    release_task_run_lock,
)


class LockAwareFakeRedis(FakeRedis):
    async def eval(self, script, numkeys, *args):
        key = args[0]
        owner_token = args[1]
        current = await self.get(key)

        if current == owner_token:
            await self.delete(key)
            return 1

        return 0


def make_redis() -> FakeRedis:
    return LockAwareFakeRedis(decode_responses=True)


def test_cache_task_status_set_and_get():
    async def scenario():
        redis = make_redis()
        try:
            await cache_task_status(
                redis,
                user_id=1,
                task_id=10,
                status="running",
                current_step=2,
                attempt=1,
                max_steps=8,
            )
            value = await get_cached_task_status(
                redis,
                user_id=1,
                task_id=10,
            )
            assert value == {
                "task_id": 10,
                "status": "running",
                "current_step": 2,
                "attempt": 1,
                "max_steps": 8,
                "current_node": None,
            }
        finally:
            await redis.aclose()

    asyncio.run(scenario())


def test_cache_task_status_ttl():
    async def scenario():
        redis = make_redis()
        try:
            await cache_task_status(
                redis,
                user_id=1,
                task_id=10,
                status="pending",
                current_step=0,
                attempt=0,
                max_steps=8,
            )
            ttl = await redis.ttl(
                "jobfit:user:1:task:10:status"
            )
            assert 1 <= ttl <= TASK_STATUS_TTL_SECONDS
        finally:
            await redis.aclose()

    asyncio.run(scenario())


def test_cache_task_status_user_and_task_isolation():
    async def scenario():
        redis = make_redis()
        try:
            await cache_task_status(
                redis,
                user_id=1,
                task_id=10,
                status="running",
                current_step=1,
                attempt=1,
                max_steps=8,
            )
            assert await get_cached_task_status(
                redis,
                user_id=2,
                task_id=10,
            ) is None
            assert await get_cached_task_status(
                redis,
                user_id=1,
                task_id=11,
            ) is None
        finally:
            await redis.aclose()

    asyncio.run(scenario())


def test_invalidate_task_status():
    async def scenario():
        redis = make_redis()
        try:
            await cache_task_status(
                redis,
                user_id=1,
                task_id=10,
                status="completed",
                current_step=3,
                attempt=1,
                max_steps=8,
            )
            await invalidate_task_status(
                redis,
                user_id=1,
                task_id=10,
            )
            assert await get_cached_task_status(
                redis,
                user_id=1,
                task_id=10,
            ) is None
        finally:
            await redis.aclose()

    asyncio.run(scenario())


def test_corrupted_cache_is_deleted():
    async def scenario():
        redis = make_redis()
        key = "jobfit:user:1:task:10:status"
        try:
            await redis.set(key, "{bad-json")
            assert await get_cached_task_status(
                redis,
                user_id=1,
                task_id=10,
            ) is None
            assert await redis.exists(key) == 0
        finally:
            await redis.aclose()

    asyncio.run(scenario())


def test_cache_missing_required_fields_is_deleted():
    async def scenario():
        redis = make_redis()
        key = "jobfit:user:1:task:10:status"
        try:
            await redis.set(key, '{"task_id": 10, "status": "running"}')
            assert await get_cached_task_status(
                redis,
                user_id=1,
                task_id=10,
            ) is None
            assert await redis.exists(key) == 0
        finally:
            await redis.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "payload",
    [
        {
            "task_id": "abc",
            "status": "running",
            "current_step": 0,
            "attempt": 0,
            "max_steps": 8,
        },
        {
            "task_id": 10,
            "status": "unknown",
            "current_step": 0,
            "attempt": 0,
            "max_steps": 8,
        },
        {
            "task_id": 10,
            "status": "running",
            "current_step": -1,
            "attempt": 0,
            "max_steps": 8,
        },
        {
            "task_id": 10,
            "status": "running",
            "current_step": 0,
            "attempt": "x",
            "max_steps": 8,
        },
        {
            "task_id": 10,
            "status": "running",
            "current_step": 0,
            "attempt": 0,
            "max_steps": 0,
        },
        {
            "task_id": 10,
            "status": "running",
            "current_step": 9,
            "attempt": 0,
            "max_steps": 8,
        },
    ],
)
def test_invalid_cache_payload_is_deleted(payload: dict):
    async def scenario():
        redis = make_redis()
        key = "jobfit:user:1:task:10:status"
        try:
            await redis.set(key, json.dumps(payload))
            assert await get_cached_task_status(
                redis,
                user_id=1,
                task_id=10,
            ) is None
            assert await redis.exists(key) == 0
        finally:
            await redis.aclose()

    asyncio.run(scenario())


def test_task_run_lock_conflict_and_owner_release():
    async def scenario():
        redis = make_redis()
        try:
            acquired = await acquire_task_run_lock(
                redis,
                task_id=10,
                owner_token="owner-a",
            )
            assert acquired is True

            second_acquire = await acquire_task_run_lock(
                redis,
                task_id=10,
                owner_token="owner-b",
            )
            assert second_acquire is False

            wrong_release = await release_task_run_lock(
                redis,
                task_id=10,
                owner_token="owner-b",
            )
            assert wrong_release is False

            ttl = await redis.ttl("jobfit:task:10:run_lock")
            assert 1 <= ttl <= RUN_LOCK_TTL_SECONDS

            correct_release = await release_task_run_lock(
                redis,
                task_id=10,
                owner_token="owner-a",
            )
            assert correct_release is True
            assert await redis.exists("jobfit:task:10:run_lock") == 0
        finally:
            await redis.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("current_step", "attempt", "ttl"),
    [
        (-1, 0, 300),
        (0, -1, 300),
        (0, 0, 0),
    ],
)
def test_cache_task_status_validates_numbers(
    current_step: int,
    attempt: int,
    ttl: int,
):
    async def scenario():
        redis = make_redis()
        try:
            with pytest.raises(ValueError):
                await cache_task_status(
                    redis,
                    user_id=1,
                    task_id=10,
                    status="pending",
                    current_step=current_step,
                    attempt=attempt,
                    max_steps=8,
                    ttl=ttl,
                )
        finally:
            await redis.aclose()

    asyncio.run(scenario())
