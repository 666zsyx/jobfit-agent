# 提供 Redis 固定窗口限流、每日请求配额和 Token 配额。

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.exceptions import RateLimitExceededError


class RateLimitDecision(BaseModel):
    allowed: bool
    scope: str
    limit: int = Field(gt=0)
    remaining: int = Field(ge=0)
    retry_after_seconds: int = Field(ge=0)
    reset_at_epoch: int = Field(ge=0)
    fallback_local: bool = False


_local_counters: dict[str, tuple[int, int]] = {}
_local_token_usage: dict[str, int] = {}
_local_lock = asyncio.Lock()


def _minute_key(user_id: int, scope: str) -> tuple[str, int]:
    window = int(time.time() // 60)
    return f"jobfit:rate:{user_id}:{scope}:{window}", window * 60 + 60


def _local_token_key(user_id: int) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    return f"{today}:{user_id}"


def _daily_key(kind: str, user_id: int) -> tuple[str, int]:
    today = datetime.now(timezone.utc).date().isoformat()
    tomorrow = (
        int(time.time() // 86400) + 1
    ) * 86400
    return f"jobfit:quota:{kind}:{user_id}:{today}", tomorrow


async def _local_consume(
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> RateLimitDecision:
    now = int(time.time())
    window = now // window_seconds
    async with _local_lock:
        stored_window, count = _local_counters.get(key, (window, 0))
        if stored_window != window:
            stored_window = window
            count = 0
        count += 1
        _local_counters[key] = (stored_window, count)

    remaining = max(limit - count, 0)
    reset_at = (window + 1) * window_seconds
    return RateLimitDecision(
        allowed=count <= limit,
        scope=key,
        limit=limit,
        remaining=remaining,
        retry_after_seconds=max(reset_at - now, 1),
        reset_at_epoch=reset_at,
        fallback_local=True,
    )


async def _consume_redis_window(
    redis: Redis,
    *,
    key: str,
    limit: int,
    window_seconds: int,
    reset_at: int,
) -> RateLimitDecision:
    value = int(await redis.incr(key))
    if value == 1:
        await redis.expire(key, window_seconds + 1)

    ttl = int(await redis.ttl(key))
    retry_after = ttl if ttl > 0 else window_seconds
    return RateLimitDecision(
        allowed=value <= limit,
        scope=key,
        limit=limit,
        remaining=max(limit - value, 0),
        retry_after_seconds=max(retry_after, 1),
        reset_at_epoch=reset_at,
    )


async def enforce_rate_limit(
    redis: Redis,
    *,
    user_id: int,
    scope: str,
    limit: int | None = None,
) -> RateLimitDecision:
    """按用户和接口执行每分钟固定窗口限流。"""

    if not settings.rate_limit_enabled:
        return RateLimitDecision(
            allowed=True,
            scope=scope,
            limit=max(limit or settings.rate_limit_requests_per_minute, 1),
            remaining=0,
            retry_after_seconds=0,
            reset_at_epoch=0,
        )

    resolved_limit = (
        limit or settings.rate_limit_requests_per_minute
    )
    key, reset_at = _minute_key(user_id, scope)
    try:
        decision = await _consume_redis_window(
            redis,
            key=key,
            limit=resolved_limit,
            window_seconds=60,
            reset_at=reset_at,
        )
    except RedisError:
        decision = await _local_consume(
            key=key,
            limit=resolved_limit,
            window_seconds=60,
        )

    if not decision.allowed:
        raise RateLimitExceededError(
            message="请求过于频繁，请稍后重试",
            retry_after_seconds=decision.retry_after_seconds,
            limit_type=f"rate:{scope}",
        )
    return decision


async def enforce_login_rate_limit(
    redis: Redis,
    *,
    client_ip: str,
    username: str,
    limit: int = 10,
    window_seconds: int = 60,
) -> RateLimitDecision:
    """按来源 IP 和用户名限制登录尝试。"""

    if not settings.rate_limit_enabled:
        return RateLimitDecision(
            allowed=True,
            scope="login",
            limit=max(limit, 1),
            remaining=0,
            retry_after_seconds=0,
            reset_at_epoch=0,
        )

    now = int(time.time())
    window = now // window_seconds
    key = (
        f"jobfit:login:{client_ip}:{username}:{window}"
    )
    reset_at = (window + 1) * window_seconds
    try:
        decision = await _consume_redis_window(
            redis,
            key=key,
            limit=limit,
            window_seconds=window_seconds,
            reset_at=reset_at,
        )
    except RedisError:
        decision = await _local_consume(
            key=key,
            limit=limit,
            window_seconds=window_seconds,
        )

    if not decision.allowed:
        raise RateLimitExceededError(
            message="登录尝试过于频繁，请稍后重试",
            retry_after_seconds=decision.retry_after_seconds,
            limit_type="login",
        )
    return decision


async def enforce_daily_request_quota(
    redis: Redis,
    *,
    user_id: int,
    limit: int | None = None,
) -> RateLimitDecision:
    """按用户执行每日请求次数配额。"""

    if not settings.rate_limit_enabled:
        return RateLimitDecision(
            allowed=True,
            scope="daily_requests",
            limit=max(limit or settings.daily_request_quota, 1),
            remaining=0,
            retry_after_seconds=0,
            reset_at_epoch=0,
        )

    resolved_limit = limit or settings.daily_request_quota
    key, reset_at = _daily_key("requests", user_id)
    try:
        decision = await _consume_redis_window(
            redis,
            key=key,
            limit=resolved_limit,
            window_seconds=86400,
            reset_at=reset_at,
        )
    except RedisError:
        decision = await _local_consume(
            key=key,
            limit=resolved_limit,
            window_seconds=86400,
        )

    if not decision.allowed:
        raise RateLimitExceededError(
            message="今日请求配额已用完",
            retry_after_seconds=decision.retry_after_seconds,
            limit_type="daily_requests",
        )
    return decision


async def get_daily_token_usage(
    redis: Redis,
    *,
    user_id: int,
) -> int:
    key, _ = _daily_key("tokens", user_id)
    try:
        raw = await redis.get(key)
    except RedisError:
        return _local_token_usage.get(_local_token_key(user_id), 0)
    if raw is None:
        return 0
    try:
        return max(int(raw), 0)
    except (TypeError, ValueError):
        return 0


async def enforce_daily_token_quota(
    redis: Redis,
    *,
    user_id: int,
    limit: int | None = None,
) -> int:
    """在请求前检查每日 Token 配额。"""

    if not settings.rate_limit_enabled:
        return 0

    used = await get_daily_token_usage(redis, user_id=user_id)
    resolved_limit = limit or settings.daily_token_quota
    if used >= resolved_limit:
        _, reset_at = _daily_key("tokens", user_id)
        raise RateLimitExceededError(
            message="今日 Token 配额已用完",
            retry_after_seconds=max(reset_at - int(time.time()), 1),
            limit_type="daily_tokens",
        )
    return used


async def record_daily_token_usage(
    redis: Redis,
    *,
    user_id: int,
    total_tokens: int,
) -> int:
    if not settings.rate_limit_enabled or total_tokens <= 0:
        return 0

    key, reset_at = _daily_key("tokens", user_id)
    try:
        value = int(await redis.incrby(key, total_tokens))
        ttl = int(await redis.ttl(key))
        if ttl <= 0:
            await redis.expire(
                key,
                max(reset_at - int(time.time()), 1),
            )
        return value
    except RedisError:
        local_key = _local_token_key(user_id)
        _local_token_usage[local_key] = (
            _local_token_usage.get(local_key, 0) + total_tokens
        )
        return _local_token_usage[local_key]


async def enforce_api_limits(
    redis: Redis,
    *,
    user_id: int,
    scope: str,
    enforce_token_quota: bool = True,
) -> None:
    await enforce_rate_limit(
        redis,
        user_id=user_id,
        scope=scope,
    )
    await enforce_daily_request_quota(redis, user_id=user_id)
    if enforce_token_quota:
        await enforce_daily_token_quota(redis, user_id=user_id)


__all__ = [
    "RateLimitDecision",
    "enforce_login_rate_limit",
    "enforce_api_limits",
    "enforce_daily_request_quota",
    "enforce_daily_token_quota",
    "enforce_rate_limit",
    "get_daily_token_usage",
    "record_daily_token_usage",
]
