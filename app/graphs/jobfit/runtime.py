# 定义 JobFit Graph 的运行时依赖上下文。

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, NotRequired, TypedDict

from app.graphs.jobfit.state import JobFitGraphState
from app.schemas.agent_events import AgentEventSink
from app.schemas.chat import LLMWithToolsResult
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


ChatWithTools = Callable[..., Awaitable[LLMWithToolsResult]]
ToolContextFactory = Callable[[JobFitGraphState, int], ToolContext]
ReportPersist = Callable[[JobFitGraphState], Awaitable[dict[str, Any]]]


class JobFitGraphContext(TypedDict):
    """调用图时注入的运行时依赖。

    这些对象包含连接、回调和内存状态，不进入 Graph State，
    因此不会被 Checkpoint 持久化。
    """

    chat_with_tools: ChatWithTools
    tool_registry: ToolRegistry
    tool_context_factory: ToolContextFactory
    event_sink: AgentEventSink | None
    persist_report: NotRequired[ReportPersist]


__all__ = [
    "ChatWithTools",
    "JobFitGraphContext",
    "ReportPersist",
    "ToolContextFactory",
]
