# 定义工具上下文、工具描述和参数契约。

import re
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auth import CurrentUser
from app.schemas.tool_audit import ToolAuditEvent


TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# 保存工具执行所需的后端可信上下文。
class ToolContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    current_user: CurrentUser
    session: AsyncSession | None = Field(default=None, exclude=True)
    task_id: int | None = None
    step_no: int | None = None
    resume_profile_snapshot: dict | None = Field(
        default=None,
        exclude=True,
    )
    pending_report: dict | None = Field(
        default=None,
        exclude=True,
    )
    defer_report_save: bool = Field(
        default=False,
        exclude=True,
    )
    collect_tool_audit: bool = Field(
        default=False,
        exclude=True,
    )
    tool_audit_events: list[ToolAuditEvent] = Field(
        default_factory=list,
        exclude=True,
    )


ToolHandler = Callable[
    [BaseModel, ToolContext],
    Awaitable[dict[str, Any]],
]


# 把工具名、说明、参数模型和异步处理函数绑定为一个契约。
class ToolSpec:
    def __init__(
        self,
        name: str,
        description: str,
        args_model: type[BaseModel],
        handler: ToolHandler,
    ):
        if not TOOL_NAME_PATTERN.fullmatch(name):
            raise ValueError(
                "工具名必须为 1～64 位，且只能包含"
                "字母、数字、下划线和短横线"
            )

        if not description.strip():
            raise ValueError("工具描述不能为空")

        self.name = name
        self.description = description
        self.args_model = args_model
        self.handler = handler

    def openai_definition(self) -> dict:
        parameters = self.args_model.model_json_schema()
        parameters["additionalProperties"] = False

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }
