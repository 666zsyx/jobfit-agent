# 验证岗位 JD 提取 Prompt、重试和异常边界。

import asyncio

import pytest
from pydantic import ValidationError

from app.core.exceptions import LLMServiceError, StructuredOutputError
from app.schemas.chat import ChatResult, TokenUsage
from app.schemas.extraction import JobExtraction
from app.services import extraction


VALID_JOB_JSON = (
    '{"responsibilities":["负责 FastAPI 后端服务开发"],'
    '"required_skills":["熟悉 Python 和 FastAPI"],'
    '"nice_to_have":["有 LLM 应用开发经验"]}'
)

INVALID_JOB_JSON = (
    '{"responsibilities":["负责 FastAPI 后端服务开发"],'
    '"required_skills":[],'
    '"nice_to_have":[]}'
)


def make_chat_result(answer: str) -> ChatResult:
    return ChatResult(
        answer=answer,
        usage=TokenUsage(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        latency_ms=10,
    )


def copy_messages(
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [message.copy() for message in messages]


def test_extract_job_returns_on_first_attempt(monkeypatch):
    calls: list[list[dict[str, str]]] = []

    async def fake_chat_json(
        messages: list[dict[str, str]],
    ) -> ChatResult:
        calls.append(copy_messages(messages))
        return make_chat_result(VALID_JOB_JSON)

    monkeypatch.setattr(extraction, "chat_json", fake_chat_json)

    result = asyncio.run(
        extraction.extract_job("负责 FastAPI 后端服务开发")
    )

    assert isinstance(result, JobExtraction)
    assert result.responsibilities == ["负责 FastAPI 后端服务开发"]
    assert result.required_skills == ["熟悉 Python 和 FastAPI"]
    assert result.nice_to_have == ["有 LLM 应用开发经验"]
    assert len(calls) == 1


def test_extract_job_retries_after_validation_error(monkeypatch):
    calls: list[list[dict[str, str]]] = []
    answers = [INVALID_JOB_JSON, VALID_JOB_JSON]

    async def fake_chat_json(
        messages: list[dict[str, str]],
    ) -> ChatResult:
        calls.append(copy_messages(messages))
        answer = answers[len(calls) - 1]
        return make_chat_result(answer)

    monkeypatch.setattr(extraction, "chat_json", fake_chat_json)

    result = asyncio.run(
        extraction.extract_job("负责 FastAPI 后端服务开发")
    )

    assert isinstance(result, JobExtraction)
    assert result.responsibilities == ["负责 FastAPI 后端服务开发"]
    assert result.required_skills == ["熟悉 Python 和 FastAPI"]
    assert len(calls) == 2

    second_messages = calls[1]
    assert len(second_messages) == 4

    assert second_messages[2] == {
        "role": "assistant",
        "content": INVALID_JOB_JSON,
    }

    feedback = second_messages[3]
    assert feedback["role"] == "user"
    assert "required_skills" in feedback["content"]
    assert "too_short" in feedback["content"]
    assert "重新输出完整" in feedback["content"]


def test_extract_job_raises_after_two_invalid_responses(monkeypatch):
    calls: list[list[dict[str, str]]] = []

    async def fake_chat_json(
        messages: list[dict[str, str]],
    ) -> ChatResult:
        calls.append(copy_messages(messages))
        return make_chat_result(INVALID_JOB_JSON)

    monkeypatch.setattr(extraction, "chat_json", fake_chat_json)

    with pytest.raises(StructuredOutputError) as exc_info:
        asyncio.run(
            extraction.extract_job("负责 FastAPI 后端服务开发")
        )

    assert len(calls) == 2
    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_extract_job_propagates_llm_service_error(monkeypatch):
    calls: list[list[dict[str, str]]] = []

    async def fake_chat_json(
        messages: list[dict[str, str]],
    ) -> ChatResult:
        calls.append(copy_messages(messages))
        raise LLMServiceError(
            message="LLM 服务暂时不可用。",
            status_code=503,
        )

    monkeypatch.setattr(extraction, "chat_json", fake_chat_json)

    with pytest.raises(LLMServiceError) as exc_info:
        asyncio.run(
            extraction.extract_job("负责 FastAPI 后端服务开发")
        )

    assert exc_info.value.status_code == 503
    assert len(calls) == 1


def test_extract_job_retries_after_empty_response(monkeypatch):
    calls: list[list[dict[str, str]]] = []
    answers = ["", VALID_JOB_JSON]

    async def fake_chat_json(
        messages: list[dict[str, str]],
    ) -> ChatResult:
        calls.append(copy_messages(messages))
        answer = answers[len(calls) - 1]
        return make_chat_result(answer)

    monkeypatch.setattr(extraction, "chat_json", fake_chat_json)

    result = asyncio.run(
        extraction.extract_job("负责 FastAPI 后端服务开发")
    )

    assert isinstance(result, JobExtraction)
    assert result.responsibilities == ["负责 FastAPI 后端服务开发"]
    assert len(calls) == 2

    second_messages = calls[1]
    assert len(second_messages) == 3
    assert second_messages[2]["role"] == "user"
    assert "响应为空" in second_messages[2]["content"]
    assert "JSON" in second_messages[2]["content"]


def test_extract_job_raises_after_two_empty_responses(monkeypatch):
    calls: list[list[dict[str, str]]] = []

    async def fake_chat_json(
        messages: list[dict[str, str]],
    ) -> ChatResult:
        calls.append(copy_messages(messages))
        return make_chat_result("")

    monkeypatch.setattr(extraction, "chat_json", fake_chat_json)

    with pytest.raises(StructuredOutputError) as exc_info:
        asyncio.run(
            extraction.extract_job("负责 FastAPI 后端服务开发")
        )

    assert len(calls) == 2
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "大模型返回内容为空"
