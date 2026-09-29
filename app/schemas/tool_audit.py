# 定义工具执行的内部审计事件。

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ToolAuditStatus = Literal[
    "started",
    "success",
    "validation_error",
    "timeout",
    "error",
    "unknown_tool",
]


class ToolAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_no: int = Field(ge=1)
    tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    status: ToolAuditStatus
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    argument_keys: list[str] = Field(default_factory=list)


__all__ = ["ToolAuditEvent", "ToolAuditStatus"]
