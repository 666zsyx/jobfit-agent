# 检查数据库、Checkpoint 和 Redis 是否就绪。

from __future__ import annotations

from sqlalchemy import text

from app.cache.client import get_redis_client
from app.db.session import engine


async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def check_checkpoint_tables() -> None:
    async with engine.connect() as connection:
        await connection.execute(
            text(
                "SELECT 1 FROM public.checkpoint_migrations LIMIT 1"
            )
        )


async def check_redis() -> None:
    redis = get_redis_client()
    await redis.ping()


async def collect_readiness() -> dict[str, str]:
    checks: dict[str, str] = {}
    failures: list[str] = []

    for name, check in (
        ("database", check_database),
        ("checkpoint", check_checkpoint_tables),
        ("redis", check_redis),
    ):
        try:
            await check()
        except Exception:
            checks[name] = "failed"
            failures.append(name)
        else:
            checks[name] = "ok"

    return {
        "status": "ready" if not failures else "not_ready",
        "checks": checks,
    }


__all__ = [
    "check_checkpoint_tables",
    "check_database",
    "check_redis",
    "collect_readiness",
]
