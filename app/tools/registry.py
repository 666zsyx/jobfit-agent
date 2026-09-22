# 提供工具白名单注册和 OpenAI 工具定义导出。

from app.tools.base import ToolSpec


# 维护工具白名单，并导出模型可识别的工具定义。
class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具已注册：{tool.name}")

        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def openai_definitions(self) -> list[dict]:
        return [
            tool.openai_definition()
            for tool in self._tools.values()
        ]
