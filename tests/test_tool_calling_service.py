# 验证一次 Function Calling 往返、消息历史和 Usage 汇总。

import asyncio
import json
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import CurrentUser
from app.schemas.chat import (
    ChatResult,
    LLMWithToolsResult,
    TokenUsage,
    ToolCall,
)
from app.services import tool_calling
from app.tools import ToolContext, ToolRegistry, ToolSpec


class EchoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)


def make_usage(
    prompt_tokens: int,
    completion_tokens: int,
) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def make_context() -> ToolContext:
    return ToolContext(
        current_user=CurrentUser(
            id=7,
            username="test_user",
            role="admin",
        )
    )


def make_tool_call(
    call_id: str,
    message: str,
    name: str = "echo_message",
) -> ToolCall:
    return ToolCall(
        id=call_id,
        name=name,
        arguments=json.dumps(
            {"message": message},
            ensure_ascii=False,
        ),
    )


def make_echo_tool(
    order: list[str] | None = None,
) -> ToolSpec:
    async def echo_handler(
        args: EchoArgs,
        context: ToolContext,
    ) -> dict[str, Any]:
        if order is not None:
            order.append(args.message)

        return {
            "message": args.message,
            "user_id": context.current_user.id,
        }

    return ToolSpec(
        name="echo_message",
        description="返回测试消息。",
        args_model=EchoArgs,
        handler=echo_handler,
    )


def make_registry(
    order: list[str] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(make_echo_tool(order))
    return registry


def test_direct_answer_calls_model_once(monkeypatch):
    calls: list[dict[str, Any]] = []
    usage = make_usage(10, 2)

    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        calls.append({"messages": messages, "tools": tools})
        return LLMWithToolsResult(
            content="直接回答",
            tool_calls=[],
            usage=usage,
            latency_ms=5,
        )

    async def fake_chat(messages: list[dict[str, Any]]) -> ChatResult:
        raise AssertionError("直接回答时不应进行第二次模型调用")

    monkeypatch.setattr(
        tool_calling,
        "chat_with_tools",
        fake_chat_with_tools,
    )
    monkeypatch.setattr(tool_calling, "chat", fake_chat)

    result = asyncio.run(
        tool_calling.run_tool_calling_once(
            messages=[{"role": "user", "content": "你好"}],
            registry=make_registry(),
            context=make_context(),
        )
    )

    assert result.answer == "直接回答"
    assert result.tool_calls == []
    assert result.tool_results == []
    assert result.usage == usage
    assert result.latency_ms >= 0
    assert len(calls) == 1


def test_one_tool_call_builds_assistant_and_tool_messages(monkeypatch):
    captured_messages: list[list[dict[str, Any]]] = []
    first_usage = make_usage(10, 2)
    second_usage = make_usage(20, 3)

    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        assert tools == make_registry().openai_definitions()
        return LLMWithToolsResult(
            content=None,
            tool_calls=[make_tool_call("call_001", "hello")],
            usage=first_usage,
            latency_ms=5,
        )

    async def fake_chat(
        messages: list[dict[str, Any]],
    ) -> ChatResult:
        captured_messages.append(messages)
        return ChatResult(
            answer="工具调用完成",
            usage=second_usage,
            latency_ms=7,
        )

    monkeypatch.setattr(
        tool_calling,
        "chat_with_tools",
        fake_chat_with_tools,
    )
    monkeypatch.setattr(tool_calling, "chat", fake_chat)

    result = asyncio.run(
        tool_calling.run_tool_calling_once(
            messages=[{"role": "user", "content": "执行工具"}],
            registry=make_registry(),
            context=make_context(),
        )
    )

    assert result.answer == "工具调用完成"
    assert [call.id for call in result.tool_calls] == ["call_001"]
    assert len(result.tool_results) == 1
    assert result.tool_results[0].tool_call_id == "call_001"
    assert result.tool_results[0].result == {
        "ok": True,
        "result": {"message": "hello", "user_id": 7},
    }
    assert result.usage == make_usage(30, 5)

    assert len(captured_messages) == 1
    messages = captured_messages[0]
    assert messages[-2] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_001",
                "type": "function",
                "function": {
                    "name": "echo_message",
                    "arguments": '{"message": "hello"}',
                },
            }
        ],
    }
    assert messages[-1]["role"] == "tool"
    assert messages[-1]["tool_call_id"] == "call_001"
    assert json.loads(messages[-1]["content"]) == {
        "ok": True,
        "result": {"message": "hello", "user_id": 7},
    }


def test_multiple_tools_execute_in_order(monkeypatch):
    order: list[str] = []
    captured_messages: list[list[dict[str, Any]]] = []

    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        return LLMWithToolsResult(
            content=None,
            tool_calls=[
                make_tool_call("call_001", "first"),
                make_tool_call("call_002", "second"),
            ],
            usage=make_usage(10, 2),
            latency_ms=5,
        )

    async def fake_chat(
        messages: list[dict[str, Any]],
    ) -> ChatResult:
        captured_messages.append(messages)
        return ChatResult(
            answer="两个工具完成",
            usage=make_usage(20, 3),
            latency_ms=7,
        )

    monkeypatch.setattr(
        tool_calling,
        "chat_with_tools",
        fake_chat_with_tools,
    )
    monkeypatch.setattr(tool_calling, "chat", fake_chat)

    result = asyncio.run(
        tool_calling.run_tool_calling_once(
            messages=[{"role": "user", "content": "执行两个工具"}],
            registry=make_registry(order),
            context=make_context(),
        )
    )

    assert order == ["first", "second"]
    assert len(result.tool_results) == 2
    assert [record.tool_call_id for record in result.tool_results] == [
        "call_001",
        "call_002",
    ]

    tool_messages = captured_messages[0][-2:]
    assert [message["tool_call_id"] for message in tool_messages] == [
        "call_001",
        "call_002",
    ]
    assert [
        json.loads(message["content"])["result"]["message"]
        for message in tool_messages
    ] == ["first", "second"]


def test_invalid_json_returns_safe_error_and_calls_model(monkeypatch):
    captured_messages: list[list[dict[str, Any]]] = []

    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        return LLMWithToolsResult(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_001",
                    name="echo_message",
                    arguments="not-json",
                )
            ],
            usage=make_usage(10, 2),
            latency_ms=5,
        )

    async def fake_chat(
        messages: list[dict[str, Any]],
    ) -> ChatResult:
        captured_messages.append(messages)
        return ChatResult(
            answer="参数解析失败",
            usage=make_usage(20, 3),
            latency_ms=7,
        )

    monkeypatch.setattr(
        tool_calling,
        "chat_with_tools",
        fake_chat_with_tools,
    )
    monkeypatch.setattr(tool_calling, "chat", fake_chat)

    result = asyncio.run(
        tool_calling.run_tool_calling_once(
            messages=[{"role": "user", "content": "非法参数"}],
            registry=make_registry(),
            context=make_context(),
        )
    )

    expected_error = {
        "ok": False,
        "error": "工具参数解析失败",
    }
    assert result.tool_results[0].result == expected_error
    assert json.loads(captured_messages[0][-1]["content"]) == expected_error


def test_unknown_tool_returns_safe_error(monkeypatch):
    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        return LLMWithToolsResult(
            content=None,
            tool_calls=[
                make_tool_call(
                    "call_001",
                    "hello",
                    name="unknown_tool",
                )
            ],
            usage=make_usage(10, 2),
            latency_ms=5,
        )

    async def fake_chat(
        messages: list[dict[str, Any]],
    ) -> ChatResult:
        return ChatResult(
            answer="未知工具",
            usage=make_usage(20, 3),
            latency_ms=7,
        )

    monkeypatch.setattr(
        tool_calling,
        "chat_with_tools",
        fake_chat_with_tools,
    )
    monkeypatch.setattr(tool_calling, "chat", fake_chat)

    result = asyncio.run(
        tool_calling.run_tool_calling_once(
            messages=[{"role": "user", "content": "调用未知工具"}],
            registry=make_registry(),
            context=make_context(),
        )
    )

    assert result.tool_results[0].result == {
        "ok": False,
        "error": "工具未注册",
    }


def test_internal_tool_error_is_not_exposed(monkeypatch):
    async def broken_handler(
        args: EchoArgs,
        context: ToolContext,
    ) -> dict[str, Any]:
        raise RuntimeError("内部数据库密码")

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="broken_tool",
            description="验证内部异常边界。",
            args_model=EchoArgs,
            handler=broken_handler,
        )
    )
    captured_messages: list[list[dict[str, Any]]] = []

    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        return LLMWithToolsResult(
            content=None,
            tool_calls=[
                make_tool_call(
                    "call_001",
                    "hello",
                    name="broken_tool",
                )
            ],
            usage=make_usage(10, 2),
            latency_ms=5,
        )

    async def fake_chat(
        messages: list[dict[str, Any]],
    ) -> ChatResult:
        captured_messages.append(messages)
        return ChatResult(
            answer="工具执行失败",
            usage=make_usage(20, 3),
            latency_ms=7,
        )

    monkeypatch.setattr(
        tool_calling,
        "chat_with_tools",
        fake_chat_with_tools,
    )
    monkeypatch.setattr(tool_calling, "chat", fake_chat)

    result = asyncio.run(
        tool_calling.run_tool_calling_once(
            messages=[{"role": "user", "content": "执行失败工具"}],
            registry=registry,
            context=make_context(),
        )
    )

    assert result.tool_results[0].result == {
        "ok": False,
        "error": "工具执行失败",
    }
    assert "内部数据库密码" not in str(captured_messages)


def test_usage_is_merged_across_two_model_calls(monkeypatch):
    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        return LLMWithToolsResult(
            content=None,
            tool_calls=[make_tool_call("call_001", "hello")],
            usage=TokenUsage(
                prompt_tokens=11,
                completion_tokens=3,
                total_tokens=14,
            ),
            latency_ms=5,
        )

    async def fake_chat(
        messages: list[dict[str, Any]],
    ) -> ChatResult:
        return ChatResult(
            answer="完成",
            usage=TokenUsage(
                prompt_tokens=19,
                completion_tokens=7,
                total_tokens=26,
            ),
            latency_ms=7,
        )

    monkeypatch.setattr(
        tool_calling,
        "chat_with_tools",
        fake_chat_with_tools,
    )
    monkeypatch.setattr(tool_calling, "chat", fake_chat)

    result = asyncio.run(
        tool_calling.run_tool_calling_once(
            messages=[{"role": "user", "content": "统计 Usage"}],
            registry=make_registry(),
            context=make_context(),
        )
    )

    assert result.usage == TokenUsage(
        prompt_tokens=30,
        completion_tokens=10,
        total_tokens=40,
    )
