# 初始化 LangGraph PostgreSQL Checkpoint 数据库表。

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.event_loop import configure_event_loop_policy
from app.db.checkpoint import setup_postgres_checkpointer

configure_event_loop_policy()


async def main() -> None:
    await setup_postgres_checkpointer()
    print("LangGraph PostgreSQL Checkpoint 初始化完成")


if __name__ == "__main__":
    asyncio.run(main())
