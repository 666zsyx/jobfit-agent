# 验证带工具模型调用的响应映射和异常边界。

import asyncio
from types import SimpleNamespace

import pytest

from app.core.exceptions import LLMServiceError
from app.services import llm


def make_usage() -> SimpleNamespace:
    return SimpleNamespace(
        prompt_tokens=12,
        completion_tokens=6,
        total_tokens=18,
    )


def make_message(
    content: str | None,
    tool_calls: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
    )


def make_response(
    message: SimpleNamespace,
    usage: SimpleNamespace | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=usage,
    )


def make_tool_call(
    call_id: str,
    name: str,
    arguments: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


def test_chat_with_tools_maps_one_tool_call(monkeypatch):
    calls = []
    messages = [{"role": "user", "content": "查询候选人档案"}]
    tools = [{"type": "function", "function": {"name": "get_profile"}}]
    arguments = '{"candidate_id": "c-001"}'

    async def fake_create(**kwargs):
        calls.append(kwargs)
        return make_response(
            message=make_message(
                content=None,
                tool_calls=[
                    make_tool_call(
                        call_id="call_001",
                        name="get_profile",
                        arguments=arguments,
                    )
                ],
            ),
            usage=make_usage(),
        )

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)

    result = asyncio.run(
        llm.chat_with_tools(
            messages=messages,
            tools=tools,
        )
    )

    assert calls == [
        {
            "model": llm.settings.llm_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }
    ]
    assert result.content is None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "call_001"
    assert result.tool_calls[0].name == "get_profile"
    assert result.tool_calls[0].arguments == arguments
    assert isinstance(result.tool_calls[0].arguments, str)
    assert result.usage.prompt_tokens == 12
    assert result.usage.completion_tokens == 6
    assert result.usage.total_tokens == 18
    assert isinstance(result.latency_ms, int)


def test_chat_with_tools_maps_multiple_tool_calls(monkeypatch):
    async def fake_create(**kwargs):
        return make_response(
            message=make_message(
                content=None,
                tool_calls=[
                    make_tool_call(
                        call_id="call_001",
                        name="get_profile",
                        arguments='{"candidate_id": "c-001"}',
                    ),
                    make_tool_call(
                        call_id="call_002",
                        name="get_job",
                        arguments='{"job_id": "j-001"}',
                    ),
                ],
            ),
            usage=make_usage(),
        )

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)

    result = asyncio.run(
        llm.chat_with_tools(
            messages=[{"role": "user", "content": "查询档案和岗位"}],
            tools=[],
        )
    )

    assert [call.id for call in result.tool_calls] == [
        "call_001",
        "call_002",
    ]
    assert [call.name for call in result.tool_calls] == [
        "get_profile",
        "get_job",
    ]
    assert [call.arguments for call in result.tool_calls] == [
        '{"candidate_id": "c-001"}',
        '{"job_id": "j-001"}',
    ]


def test_chat_with_tools_allows_text_without_tool_calls(monkeypatch):
    async def fake_create(**kwargs):
        return make_response(
            message=make_message(
                content="这是一个直接回答。",
                tool_calls=None,
            ),
            usage=make_usage(),
        )

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)

    result = asyncio.run(
        llm.chat_with_tools(
            messages=[{"role": "user", "content": "直接回答"}],
            tools=[],
        )
    )

    assert result.content == "这是一个直接回答。"
    assert result.tool_calls == []


@pytest.mark.parametrize("content", [None, "", "   "])
def test_chat_with_tools_rejects_empty_message(
    monkeypatch,
    content: str | None,
):
    async def fake_create(**kwargs):
        return make_response(
            message=make_message(
                content=content,
                tool_calls=None,
            ),
            usage=make_usage(),
        )

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)

    with pytest.raises(LLMServiceError):
        asyncio.run(
            llm.chat_with_tools(
                messages=[{"role": "user", "content": "空响应"}],
                tools=[],
            )
        )


def test_chat_with_tools_rejects_missing_usage(monkeypatch):
    async def fake_create(**kwargs):
        return make_response(
            message=make_message(
                content=None,
                tool_calls=[
                    make_tool_call(
                        call_id="call_001",
                        name="get_profile",
                        arguments="{}",
                    )
                ],
            ),
            usage=None,
        )

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)

    with pytest.raises(LLMServiceError):
        asyncio.run(
            llm.chat_with_tools(
                messages=[{"role": "user", "content": "查询档案"}],
                tools=[],
            )
        )


def test_chat_with_tools_preserves_arguments_as_json_string(monkeypatch):
    arguments = '{"candidate_id": "c-002", "include_history": true}'

    async def fake_create(**kwargs):
        return make_response(
            message=make_message(
                content=None,
                tool_calls=[
                    make_tool_call(
                        call_id="call_002",
                        name="get_profile",
                        arguments=arguments,
                    )
                ],
            ),
            usage=make_usage(),
        )

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)

    result = asyncio.run(
        llm.chat_with_tools(
            messages=[{"role": "user", "content": "查询候选人 c-002"}],
            tools=[],
        )
    )

    assert result.tool_calls[0].arguments == arguments
    assert isinstance(result.tool_calls[0].arguments, str)
