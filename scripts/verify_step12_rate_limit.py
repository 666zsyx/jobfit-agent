# 使用 FakeRedis 验证限流和配额逻辑。

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from fakeredis.aioredis import FakeRedis

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.core.exceptions import RateLimitExceededError
from app.services.rate_limit import (
    enforce_daily_request_quota,
    enforce_daily_token_quota,
    enforce_rate_limit,
    record_daily_token_usage,
)


async def main() -> None:
    original = settings.rate_limit_enabled
    settings.rate_limit_enabled = True
    redis = FakeRedis()
    report = {}
    try:
        first = await enforce_rate_limit(
            redis,
            user_id=9001,
            scope="verify",
            limit=2,
        )
        second = await enforce_rate_limit(
            redis,
            user_id=9001,
            scope="verify",
            limit=2,
        )
        blocked = False
        try:
            await enforce_rate_limit(
                redis,
                user_id=9001,
                scope="verify",
                limit=2,
            )
        except RateLimitExceededError:
            blocked = True
        report["rate_limit"] = {
            "first_remaining": first.remaining,
            "second_remaining": second.remaining,
            "blocked": blocked,
        }

        await enforce_daily_request_quota(
            redis,
            user_id=9002,
            limit=1,
        )
        request_quota_blocked = False
        try:
            await enforce_daily_request_quota(
                redis,
                user_id=9002,
                limit=1,
            )
        except RateLimitExceededError:
            request_quota_blocked = True
        report["daily_request_quota"] = {
            "blocked": request_quota_blocked,
        }

        await record_daily_token_usage(
            redis,
            user_id=9003,
            total_tokens=90,
        )
        used = await enforce_daily_token_quota(
            redis,
            user_id=9003,
            limit=100,
        )
        await record_daily_token_usage(
            redis,
            user_id=9003,
            total_tokens=20,
        )
        token_quota_blocked = False
        try:
            await enforce_daily_token_quota(
                redis,
                user_id=9003,
                limit=100,
            )
        except RateLimitExceededError:
            token_quota_blocked = True
        report["daily_token_quota"] = {
            "used_before": used,
            "blocked": token_quota_blocked,
        }

        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        settings.rate_limit_enabled = original
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
