# 定义 Agent 执行过程中可流式发送的安全事件。

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AgentEventType = Literal[
    "task_started",
    "step_started",
    "tool_started",
    "tool_finished",
    "retrieval_started",
    "retrieval_finished",
    "index_started",
    "index_finished",
    "index_failed",
    "content",
    "task_completed",
    "task_interrupted",
    "task_failed",
    "heartbeat",
    "error",
]


class AgentEvent(BaseModel):
    """不包含隐藏思维链和敏感正文的 Agent 流式事件。"""

    model_config = ConfigDict(extra="forbid")

    type: AgentEventType
    task_id: int | None = Field(default=None, gt=0)
    step: int | None = Field(default=None, ge=1)
    tool_call_id: str | None = None
    tool_name: str | None = None
    content: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


AgentEventSink = Callable[[AgentEvent], Awaitable[None]]


def format_sse_event(event: AgentEvent) -> str:
    """把 Pydantic 事件编码为 SSE 帧。"""

    return (
        f"event: {event.type}\n"
        f"data: {event.model_dump_json()}\n\n"
    )


__all__ = [
    "AgentEvent",
    "AgentEventSink",
    "AgentEventType",
    "format_sse_event",
]
