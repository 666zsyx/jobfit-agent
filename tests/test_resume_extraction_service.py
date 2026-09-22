import asyncio

import pytest
from pydantic import ValidationError

from app.core.exceptions import LLMServiceError, StructuredOutputError
from app.schemas.chat import ChatResult, TokenUsage
from app.schemas.resume import ResumeExtraction
from app.services import resume_extraction


VALID_RESUME_JSON = (
    '{"sections":['
    '{"section_type":"education","title":"教育经历",'
    '"content":"某大学 计算机科学"},'
    '{"section_type":"project_experience","title":"项目经历",'
    '"content":"使用 FastAPI 开发简历匹配服务"}'
    ']}'
)

INVALID_RESUME_JSON = (
    '{"sections":[]}'
)


def make_chat_result(answer: str) -> ChatResult:
    return ChatResult(
        answer=answer,
        usage=TokenUsage(
            prompt_tokens=20,
            completion_tokens=10,
            total_tokens=30,
        ),
        latency_ms=10,
    )


def copy_messages(
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [message.copy() for message in messages]


def test_extract_resume_sections_returns_on_first_attempt(monkeypatch):
    calls: list[list[dict[str, str]]] = []

    async def fake_chat_json(
        messages: list[dict[str, str]],
    ) -> ChatResult:
        calls.append(copy_messages(messages))
        return make_chat_result(VALID_RESUME_JSON)

    monkeypatch.setattr(
        resume_extraction,
        "chat_json",
        fake_chat_json,
    )

    result = asyncio.run(
        resume_extraction.extract_resume_sections(
            "教育经历\n某大学 计算机科学\n"
            "项目经历\n使用 FastAPI 开发简历匹配服务"
        )
    )

    assert isinstance(result, ResumeExtraction)
    assert len(result.sections) == 2
    assert result.sections[0].section_type == "education"
    assert result.sections[0].content == "某大学 计算机科学"
    assert result.sections[1].section_type == "project_experience"
    assert len(calls) == 1


def test_extract_resume_sections_retries_after_validation_error(
    monkeypatch,
):
    calls: list[list[dict[str, str]]] = []
    answers = [INVALID_RESUME_JSON, VALID_RESUME_JSON]

    async def fake_chat_json(
        messages: list[dict[str, str]],
    ) -> ChatResult:
        calls.append(copy_messages(messages))
        answer = answers[len(calls) - 1]
        return make_chat_result(answer)

    monkeypatch.setattr(
        resume_extraction,
        "chat_json",
        fake_chat_json,
    )

    result = asyncio.run(
        resume_extraction.extract_resume_sections("有效简历原文")
    )

    assert len(result.sections) == 2
    assert len(calls) == 2

    second_messages = calls[1]
    assert len(second_messages) == 4
    assert second_messages[2] == {
        "role": "assistant",
        "content": INVALID_RESUME_JSON,
    }

    feedback = second_messages[3]
    assert feedback["role"] == "user"
    assert "sections" in feedback["content"]
    assert "too_short" in feedback["content"]
    assert "重新输出完整" in feedback["content"]
    assert "不得总结或改写原文" in feedback["content"]


def test_extract_resume_sections_raises_after_two_invalid_responses(
    monkeypatch,
):
    calls: list[list[dict[str, str]]] = []

    async def fake_chat_json(
        messages: list[dict[str, str]],
    ) -> ChatResult:
        calls.append(copy_messages(messages))
        return make_chat_result(INVALID_RESUME_JSON)

    monkeypatch.setattr(
        resume_extraction,
        "chat_json",
        fake_chat_json,
    )

    with pytest.raises(StructuredOutputError) as exc_info:
        asyncio.run(
            resume_extraction.extract_resume_sections("有效简历原文")
        )

    assert len(calls) == 2
    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_extract_resume_sections_retries_after_empty_response(
    monkeypatch,
):
    calls: list[list[dict[str, str]]] = []
    answers = ["", VALID_RESUME_JSON]

    async def fake_chat_json(
        messages: list[dict[str, str]],
    ) -> ChatResult:
        calls.append(copy_messages(messages))
        answer = answers[len(calls) - 1]
        return make_chat_result(answer)

    monkeypatch.setattr(
        resume_extraction,
        "chat_json",
        fake_chat_json,
    )

    result = asyncio.run(
        resume_extraction.extract_resume_sections("有效简历原文")
    )

    assert len(result.sections) == 2
    assert len(calls) == 2

    second_messages = calls[1]
    assert len(second_messages) == 3
    assert second_messages[2]["role"] == "user"
    assert "响应为空" in second_messages[2]["content"]
    assert "不得总结或改写原文" in second_messages[2]["content"]


def test_extract_resume_sections_raises_after_two_empty_responses(
    monkeypatch,
):
    calls: list[list[dict[str, str]]] = []

    async def fake_chat_json(
        messages: list[dict[str, str]],
    ) -> ChatResult:
        calls.append(copy_messages(messages))
        return make_chat_result("")

    monkeypatch.setattr(
        resume_extraction,
        "chat_json",
        fake_chat_json,
    )

    with pytest.raises(StructuredOutputError) as exc_info:
        asyncio.run(
            resume_extraction.extract_resume_sections("有效简历原文")
        )

    assert len(calls) == 2
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "大模型返回内容为空"


def test_extract_resume_sections_propagates_llm_service_error(
    monkeypatch,
):
    calls: list[list[dict[str, str]]] = []

    async def fake_chat_json(
        messages: list[dict[str, str]],
    ) -> ChatResult:
        calls.append(copy_messages(messages))
        raise LLMServiceError(
            message="LLM 服务暂时不可用。",
            status_code=503,
        )

    monkeypatch.setattr(
        resume_extraction,
        "chat_json",
        fake_chat_json,
    )

    with pytest.raises(LLMServiceError) as exc_info:
        asyncio.run(
            resume_extraction.extract_resume_sections("有效简历原文")
        )

    assert exc_info.value.status_code == 503
    assert len(calls) == 1


@pytest.mark.parametrize("resume_text", ["", "   ", "\n\t"])
def test_extract_resume_sections_rejects_blank_text(resume_text: str):
    with pytest.raises(ValueError, match="resume_text 不能为空"):
        asyncio.run(
            resume_extraction.extract_resume_sections(resume_text)
        )


def test_extract_resume_sections_rejects_too_long_text():
    resume_text = "a" * (
        resume_extraction.MAX_RESUME_TEXT_LENGTH + 1
    )

    with pytest.raises(ValueError, match="不能超过"):
        asyncio.run(
            resume_extraction.extract_resume_sections(resume_text)
        )


def test_resume_extraction_rejects_empty_sections():
    with pytest.raises(ValidationError):
        ResumeExtraction.model_validate_json(INVALID_RESUME_JSON)


def test_resume_extraction_rejects_invalid_section_type():
    invalid_json = (
        '{"sections":[{"section_type":"工作",'
        '"title":"工作经历","content":"某公司后端开发"}]}'
    )

    with pytest.raises(ValidationError):
        ResumeExtraction.model_validate_json(invalid_json)


def test_resume_section_rejects_extra_fields():
    invalid_json = (
        '{"sections":[{"section_type":"summary",'
        '"title":"个人简介","content":"后端开发",'
        '"user_id":999}]}'
    )

    with pytest.raises(ValidationError):
        ResumeExtraction.model_validate_json(invalid_json)
