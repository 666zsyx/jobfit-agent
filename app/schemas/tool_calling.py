# 定义一次 Function Calling 往返的最终结果。

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.chat import ToolCall, TokenUsage

# 记录一次工具调用在后端的执行结果。
#工具调用在后端的执行结果
class ToolExecutionRecord(BaseModel):
    tool_call_id: str
    name: str
    result: dict[str, Any]

# 表示一次 Function Calling 往返的最终回答、工具记录和 Usage。
#一次完整 Function Calling 往返的最终结果
class ToolCallingResult(BaseModel):
    answer: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolExecutionRecord] = Field(default_factory=list)
    usage: TokenUsage
    latency_ms: int