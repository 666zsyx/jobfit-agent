# 配置兼容 psycopg 异步连接的事件循环策略。

import asyncio
import sys


def configure_event_loop_policy() -> None:
    """在 Windows 上使用 Selector 事件循环。

    psycopg 3 的异步连接不支持 Windows ProactorEventLoop。
    LangGraph PostgreSQL Checkpoint 依赖 psycopg，因此应用启动前
    必须切换到 SelectorEventLoop。
    """

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )


__all__ = ["configure_event_loop_policy"]
