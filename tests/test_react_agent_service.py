# 验证 ReAct 主循环的模型调用、工具消息和 Usage 累计。

import asyncio
import json
from typing import Any

import pytest

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import CurrentUser
from app.schemas.chat import (
    LLMWithToolsResult,
    TokenUsage,
    ToolCall,
)
from app.services import react_agent
from app.tools import ToolContext, ToolRegistry, ToolSpec


class EchoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1)


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


def make_audit_context() -> ToolContext:
    return ToolContext(
        current_user=CurrentUser(
            id=7,
            username="test_user",
            role="admin",
        ),
        collect_tool_audit=True,
    )


def make_tool_call(
    call_id: str,
    value: str,
    tool_name: str = "echo_tool",
) -> ToolCall:
    return ToolCall(
        id=call_id,
        name=tool_name,
        arguments=json.dumps(
            {"value": value},
            ensure_ascii=False,
        ),
    )


def make_registry(
    executed: list[str] | None = None,
) -> ToolRegistry:
    async def echo_handler(
        args: EchoArgs,
        context: ToolContext,
    ) -> dict[str, Any]:
        if executed is not None:
            executed.append(args.value)

        return {
            "value": args.value,
            "user_id": context.current_user.id,
        }

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="echo_tool",
            description="返回测试参数和用户 ID。",
            args_model=EchoArgs,
            handler=echo_handler,
        )
    )
    return registry


def test_direct_answer_calls_model_once(monkeypatch):
    calls: list[list[dict[str, Any]]] = []
    usage = make_usage(10, 2)

    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        calls.append([*messages])
        return LLMWithToolsResult(
            content="直接回答",
            tool_calls=[],
            usage=usage,
            latency_ms=5,
        )

    monkeypatch.setattr(
        react_agent,
        "chat_with_tools",
        fake_chat_with_tools,
    )

    result = asyncio.run(
        react_agent.run_react_loop(
            messages=[{"role": "user", "content": "你好"}],
            registry=make_registry(),
            context=make_context(),
        )
    )

    assert result.answer == "直接回答"
    assert result.status == "completed"
    assert result.steps == 1
    assert result.trace == []
    assert result.usage == usage
    assert result.latency_ms >= 0
    assert len(calls) == 1


def test_two_tool_calls_build_full_message_history(monkeypatch):
    captured_calls: list[list[dict[str, Any]]] = []
    executed: list[str] = []
    registry = make_registry(executed)
    responses = iter(
        [
            LLMWithToolsResult(
                content=None,
                tool_calls=[make_tool_call("call_001", "hello")],
                usage=make_usage(10, 2),
                latency_ms=5,
            ),
            LLMWithToolsResult(
                content=None,
                tool_calls=[make_tool_call("call_002", "world")],
                usage=make_usage(20, 3),
                latency_ms=5,
            ),
            LLMWithToolsResult(
                content="分析完成",
                tool_calls=[],
                usage=make_usage(30, 4),
                latency_ms=5,
            ),
        ]
    )

    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        assert tools == registry.openai_definitions()
        captured_calls.append([*messages])
        return next(responses)

    monkeypatch.setattr(
        react_agent,
        "chat_with_tools",
        fake_chat_with_tools,
    )

    result = asyncio.run(
        react_agent.run_react_loop(
            messages=[{"role": "user", "content": "开始分析"}],
            registry=registry,
            context=make_context(),
        )
    )

    assert result.answer == "分析完成"
    assert result.status == "completed"
    assert result.steps == 3
    assert [item.step for item in result.trace] == [1, 2]
    assert [item.tool_call_id for item in result.trace] == [
        "call_001",
        "call_002",
    ]
    assert [item.tool_name for item in result.trace] == [
        "echo_tool",
        "echo_tool",
    ]
    assert [item.arguments for item in result.trace] == [
        {"value": "hello"},
        {"value": "world"},
    ]
    assert executed == ["hello", "world"]
    assert result.usage == make_usage(60, 9)
    assert [message["role"] for message in captured_calls[2]] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
    ]



def test_max_steps_reached_stops_before_next_model_call(monkeypatch):
    call_count = 0
    registry = make_registry()

    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        nonlocal call_count
        call_count += 1
        assert tools == registry.openai_definitions()
        return LLMWithToolsResult(
            content=None,
            tool_calls=[
                make_tool_call(
                    f"call_{call_count:03d}",
                    f"value-{call_count}",
                )
            ],
            usage=make_usage(10, 1),
            latency_ms=5,
        )

    monkeypatch.setattr(
        react_agent,
        "chat_with_tools",
        fake_chat_with_tools,
    )

    result = asyncio.run(
        react_agent.run_react_loop(
            messages=[{"role": "user", "content": "不要停止"}],
            registry=registry,
            context=make_context(),
            max_steps=2,
        )
    )

    assert result.answer is None
    assert result.status == "max_steps_reached"
    assert result.steps == 2
    assert result.max_steps == 2
    assert len(result.trace) == 2
    assert call_count == 2


def test_invalid_max_steps_is_rejected():
    with pytest.raises(ValueError, match="max_steps"):
        asyncio.run(
            react_agent.run_react_loop(
                messages=[{"role": "user", "content": "测试"}],
                registry=make_registry(),
                context=make_context(),
                max_steps=0,
            )
        )


def test_invalid_json_becomes_safe_tool_observation(monkeypatch):
    captured_messages: list[list[dict[str, Any]]] = []
    executed: list[str] = []
    call_count = 0

    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        nonlocal call_count
        call_count += 1
        captured_messages.append([*messages])

        if call_count == 1:
            return LLMWithToolsResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_bad",
                        name="echo_tool",
                        arguments="{bad-json",
                    )
                ],
                usage=make_usage(10, 1),
                latency_ms=5,
            )

        return LLMWithToolsResult(
            content="参数有误",
            tool_calls=[],
            usage=make_usage(20, 2),
            latency_ms=5,
        )

    monkeypatch.setattr(
        react_agent,
        "chat_with_tools",
        fake_chat_with_tools,
    )

    audit_context = make_audit_context()
    result = asyncio.run(
        react_agent.run_react_loop(
            messages=[{"role": "user", "content": "测试坏参数"}],
            registry=make_registry(executed),
            context=audit_context,
        )
    )

    assert result.status == "completed"
    assert result.answer == "参数有误"
    assert result.trace[0].arguments is None
    assert result.trace[0].result == {
        "ok": False,
        "error": "工具参数解析失败",
    }
    assert executed == []
    assert json.loads(captured_messages[1][-1]["content"]) == {
        "ok": False,
        "error": "工具参数解析失败",
    }
    assert len(audit_context.tool_audit_events) == 1
    event = audit_context.tool_audit_events[0]
    assert event.status == "validation_error"
    assert event.step_no == 1
    assert event.tool_call_id == "call_bad"
    assert event.error_code == "invalid_tool_arguments"


def test_react_passes_step_and_tool_call_id_to_executor(monkeypatch):
    calls: list[dict[str, Any]] = []
    call_count = 0

    async def fake_execute_tool(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "result": {"value": "hello"}}

    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            return LLMWithToolsResult(
                content=None,
                tool_calls=[make_tool_call("call_audit", "hello")],
                usage=make_usage(10, 1),
                latency_ms=5,
            )

        return LLMWithToolsResult(
            content="完成",
            tool_calls=[],
            usage=make_usage(20, 2),
            latency_ms=5,
        )

    monkeypatch.setattr(
        react_agent,
        "execute_tool",
        fake_execute_tool,
    )
    monkeypatch.setattr(
        react_agent,
        "chat_with_tools",
        fake_chat_with_tools,
    )

    asyncio.run(
        react_agent.run_react_loop(
            messages=[{"role": "user", "content": "测试调用 ID"}],
            registry=make_registry(),
            context=make_audit_context(),
        )
    )

    assert len(calls) == 1
    assert calls[0]["step_no"] == 1
    assert calls[0]["tool_call_id"] == "call_audit"


def test_unknown_tool_is_recorded_and_loop_can_finish(monkeypatch):
    captured_messages: list[list[dict[str, Any]]] = []
    executed: list[str] = []
    call_count = 0

    async def fake_chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        nonlocal call_count
        call_count += 1
        captured_messages.append([*messages])

        if call_count == 1:
            return LLMWithToolsResult(
                content=None,
                tool_calls=[
                    make_tool_call(
                        "call_unknown",
                        "ignored",
                        tool_name="unknown_tool",
                    )
                ],
                usage=make_usage(10, 1),
                latency_ms=5,
            )

        return LLMWithToolsResult(
            content="未知工具已安全处理",
            tool_calls=[],
            usage=make_usage(20, 2),
            latency_ms=5,
        )

    monkeypatch.setattr(
        react_agent,
        "chat_with_tools",
        fake_chat_with_tools,
    )

    result = asyncio.run(
        react_agent.run_react_loop(
            messages=[{"role": "user", "content": "测试未知工具"}],
            registry=make_registry(executed),
            context=make_context(),
        )
    )

    assert result.status == "completed"
    assert result.answer == "未知工具已安全处理"
    assert result.trace[0].tool_name == "unknown_tool"
    assert result.trace[0].result == {
        "ok": False,
        "error": "工具未注册",
    }
    assert executed == []
    assert json.loads(captured_messages[1][-1]["content"]) == {
        "ok": False,
        "error": "工具未注册",
    }
