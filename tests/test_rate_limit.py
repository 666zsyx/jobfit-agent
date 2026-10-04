# 验证 Redis 限流、每日请求配额和 Token 配额。

import pytest
from fakeredis.aioredis import FakeRedis

import app.dependencies.rate_limit as rate_limit_dependency
from app.core.config import settings
from app.core.exceptions import RateLimitExceededError
from app.services.rate_limit import (
    enforce_daily_request_quota,
    enforce_daily_token_quota,
    enforce_rate_limit,
    record_daily_token_usage,
    record_task_token_usage,
)


def test_enforce_rate_limit_allows_then_blocks(monkeypatch) -> None:
    import asyncio

    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    async def scenario():
        redis = FakeRedis()
        try:
            first = await enforce_rate_limit(
                redis,
                user_id=101,
                scope="test",
                limit=2,
            )
            second = await enforce_rate_limit(
                redis,
                user_id=101,
                scope="test",
                limit=2,
            )
            assert first.allowed is True
            assert second.remaining == 0

            with pytest.raises(RateLimitExceededError):
                await enforce_rate_limit(
                    redis,
                    user_id=101,
                    scope="test",
                    limit=2,
                )
        finally:
            await redis.aclose()

    asyncio.run(scenario())


def test_daily_request_quota_blocks_after_limit(monkeypatch) -> None:
    import asyncio

    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    async def scenario():
        redis = FakeRedis()
        try:
            await enforce_daily_request_quota(
                redis,
                user_id=102,
                limit=1,
            )
            with pytest.raises(RateLimitExceededError):
                await enforce_daily_request_quota(
                    redis,
                    user_id=102,
                    limit=1,
                )
        finally:
            await redis.aclose()

    asyncio.run(scenario())


def test_daily_token_quota_uses_recorded_usage(monkeypatch) -> None:
    import asyncio

    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    async def scenario():
        redis = FakeRedis()
        try:
            await record_daily_token_usage(
                redis,
                user_id=103,
                total_tokens=90,
            )
            used = await enforce_daily_token_quota(
                redis,
                user_id=103,
                limit=100,
            )
            assert used == 90

            await record_daily_token_usage(
                redis,
                user_id=103,
                total_tokens=20,
            )
            with pytest.raises(RateLimitExceededError):
                await enforce_daily_token_quota(
                    redis,
                    user_id=103,
                    limit=100,
                )
        finally:
            await redis.aclose()

    asyncio.run(scenario())


def test_rate_limit_error_returns_429(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    async def reject_request(*args, **kwargs):
        raise RateLimitExceededError(
            message="请求过于频繁",
            retry_after_seconds=7,
            limit_type="rate:chat",
        )

    monkeypatch.setattr(
        rate_limit_dependency,
        "enforce_api_limits",
        reject_request,
    )

    response = client.post(
        "/api/chat",
        headers=auth_headers,
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "7"
    assert response.json()["data"]["limit_type"] == "rate:chat"

def test_read_rate_limit_can_skip_token_quota(monkeypatch) -> None:
    import asyncio
    from types import SimpleNamespace

    calls = []

    async def fake_enforce_api_limits(redis, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        rate_limit_dependency,
        "enforce_api_limits",
        fake_enforce_api_limits,
    )
    dependency = rate_limit_dependency.make_rate_limit_dependency(
        "test_read",
        enforce_token_quota=False,
        enforce_request_quota=False,
    )

    asyncio.run(
        dependency(
            current_user=SimpleNamespace(id=101),
        )
    )

    assert calls == [
        {
            "user_id": 101,
            "scope": "test_read",
            "enforce_token_quota": False,
            "enforce_request_quota": False,
        }
    ]

def test_task_token_usage_records_only_cumulative_delta(
    monkeypatch,
) -> None:
    import asyncio

    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    async def scenario():
        redis = FakeRedis()
        try:
            await record_task_token_usage(
                redis,
                user_id=104,
                task_id=9001,
                total_tokens=100,
            )
            await record_task_token_usage(
                redis,
                user_id=104,
                task_id=9001,
                total_tokens=140,
            )
            await record_task_token_usage(
                redis,
                user_id=104,
                task_id=9001,
                total_tokens=140,
            )

            from app.services.rate_limit import get_daily_token_usage

            assert await get_daily_token_usage(
                redis,
                user_id=104,
            ) == 140
        finally:
            await redis.aclose()

    asyncio.run(scenario())
