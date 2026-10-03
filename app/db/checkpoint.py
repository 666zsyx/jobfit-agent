# 提供 LangGraph PostgreSQL Checkpoint 的连接和线程配置。

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings


ASYNCPG_PREFIX = "postgresql+asyncpg://"
PSYCOPG_PREFIX = "postgresql+psycopg://"


def to_psycopg_conn_string(database_url: str | None = None) -> str:
    """把 SQLAlchemy 异步 URL 转换为 psycopg 连接串。"""

    value = (database_url or settings.database_url).strip()
    if not value:
        raise ValueError("database_url 不能为空")

    if value.startswith(ASYNCPG_PREFIX):
        return value.replace(
            ASYNCPG_PREFIX,
            "postgresql://",
            1,
        )

    if value.startswith(PSYCOPG_PREFIX):
        return value.replace(
            PSYCOPG_PREFIX,
            "postgresql://",
            1,
        )

    if value.startswith("postgresql://"):
        return value

    raise ValueError("database_url 必须是 PostgreSQL 连接串")


def checkpoint_thread_id(
    task_id: int,
    attempt: int | None = None,
) -> str:
    """为分析任务生成稳定的 Checkpoint 线程 ID。"""

    if task_id <= 0:
        raise ValueError("task_id 必须大于 0")

    if attempt is None:
        return f"jobfit-task-{task_id}"

    if attempt <= 0:
        raise ValueError("attempt 必须大于 0")

    return f"jobfit-task-{task_id}-attempt-{attempt}"


def build_checkpoint_config(
    task_id: int,
    attempt: int | None = None,
) -> dict[str, Any]:
    """生成 LangGraph 调用需要的 config。"""

    return {
        "configurable": {
            "thread_id": checkpoint_thread_id(task_id, attempt),
        }
    }


@asynccontextmanager
async def open_postgres_checkpointer(
    database_url: str | None = None,
    *,
    setup: bool = False,
) -> AsyncIterator[AsyncPostgresSaver]:
    """打开 AsyncPostgresSaver，并可选初始化 Checkpoint 表。"""

    conn_string = to_psycopg_conn_string(database_url)

    async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
        if setup:
            await saver.setup()
        yield saver


async def setup_postgres_checkpointer(
    database_url: str | None = None,
) -> None:
    """初始化 LangGraph PostgreSQL Checkpoint 表。"""

    async with open_postgres_checkpointer(
        database_url,
        setup=True,
    ):
        pass


__all__ = [
    "build_checkpoint_config",
    "checkpoint_thread_id",
    "open_postgres_checkpointer",
    "setup_postgres_checkpointer",
    "to_psycopg_conn_string",
]
