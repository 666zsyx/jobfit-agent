import re
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from app.schemas.auth import CurrentUser


TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ToolContext(BaseModel):
    current_user: CurrentUser


ToolHandler = Callable[
    [BaseModel, ToolContext],
    Awaitable[dict[str, Any]],
]


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
