from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResult(BaseModel):
    answer: str
    usage: TokenUsage
    latency_ms: int


class LLMStreamEvent(BaseModel):
    type: Literal["content", "usage"]
    content: str | None = None
    usage: TokenUsage | None = None
    latency_ms: int | None = None