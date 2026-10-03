# 定义聊天、Token Usage 和工具调用相关的数据结构。

from typing import Literal

from pydantic import BaseModel, Field


# 表示一条客户端聊天消息。
MAX_CHAT_MESSAGE_LENGTH = 20_000
MAX_CHAT_MESSAGES = 50


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(
        min_length=1,
        max_length=MAX_CHAT_MESSAGE_LENGTH,
    )


# 表示非流式聊天请求。
class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(
        min_length=1,
        max_length=MAX_CHAT_MESSAGES,
    )


# 表示一次模型调用的输入、输出和总 Token。
class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


# 表示普通聊天服务的最终文本、Usage 和耗时。
class ChatResult(BaseModel):
    answer: str
    usage: TokenUsage
    latency_ms: int


# 表示 SSE 流式聊天中的内容或 Usage 事件。
class LLMStreamEvent(BaseModel):
    type: Literal["content", "usage"]
    content: str | None = None
    usage: TokenUsage | None = None
    latency_ms: int | None = None

# 表示模型提出的一次工具调用，但 arguments 仍保留 JSON 字符串。
class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str


# 表示第一次带工具模型调用的稳定项目内响应。
class LLMWithToolsResult(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage
    latency_ms: int