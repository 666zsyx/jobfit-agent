# 验证 Agent SSE 事件和 ReAct 过程事件。

import asyncio
import json
from types import SimpleNamespace

from pydantic import BaseModel

from app.schemas.agent_events import AgentEvent, format_sse_event
from app.schemas.auth import CurrentUser
from app.schemas.chat import LLMWithToolsResult, TokenUsage, ToolCall
from app.services import react_agent
from app.services.conversation_context import (
    build_compressed_conversation_context,
)
from app.tools import ToolContext, ToolRegistry, ToolSpec


def make_usage() -> TokenUsage:
    return TokenUsage(
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
    )


def test_format_sse_event() -> None:
    frame = format_sse_event(
        AgentEvent(
            type="content",
            task_id=1,
            content="hello",
        )
    )

    assert frame.startswith("event: content\ndata: ")
    assert frame.endswith("\n\n")
    data = json.loads(frame.split("data: ", 1)[1])
    assert data["type"] == "content"
    assert data["content"] == "hello"


def test_react_loop_emits_tool_and_content_events(monkeypatch) -> None:
    class EchoArgs(BaseModel):
        pass

    async def echo_handler(args, context):
        return {"echo": "ok"}

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="echo",
            description="test",
            args_model=EchoArgs,
            handler=echo_handler,
        )
    )

    responses = iter(
        [
            LLMWithToolsResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="echo",
                        arguments="{}",
                    )
                ],
                usage=make_usage(),
                latency_ms=1,
            ),
            LLMWithToolsResult(
                content="done",
                tool_calls=[],
                usage=make_usage(),
                latency_ms=1,
            ),
        ]
    )

    async def fake_chat_with_tools(*, messages, tools):
        return next(responses)

    monkeypatch.setattr(
        react_agent,
        "chat_with_tools",
        fake_chat_with_tools,
    )
    events = []

    async def sink(event):
        events.append(event)

    result = asyncio.run(
        react_agent.run_react_loop(
            messages=[{"role": "user", "content": "hi"}],
            registry=registry,
            context=ToolContext(
                current_user=CurrentUser(
                    id=1,
                    username="demo_user",
                    role="admin",
                )
            ),
            event_sink=sink,
        )
    )

    assert result.answer == "done"
    assert [event.type for event in events] == [
        "step_started",
        "tool_started",
        "tool_finished",
        "step_started",
        "content",
    ]


def test_compressed_context_keeps_recent_messages() -> None:
    messages = [
        SimpleNamespace(role="user", content="a" * 20),
        SimpleNamespace(role="assistant", content="b" * 20),
        SimpleNamespace(role="user", content="newest"),
    ]

    result = build_compressed_conversation_context(
        messages,
        max_chars=30,
        message_max_chars=20,
    )

    assert "[较早会话已省略]" in result
    assert "user: newest" in result
    assert "a" * 20 not in result
