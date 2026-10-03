# 对比手写 ReAct 与 LangGraph 版本的核心行为。

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field

from app.graphs.jobfit import JobFitGraphContext, build_jobfit_graph
from app.schemas.agent_events import AgentEvent
from app.schemas.auth import CurrentUser
from app.schemas.chat import LLMWithToolsResult, TokenUsage, ToolCall
from app.services import react_agent
from app.services.react_agent import (
    JOBFIT_REACT_SYSTEM_PROMPT,
    build_jobfit_react_messages,
    run_react_loop,
)
from app.tools import ToolContext, ToolRegistry, ToolSpec


CORE_EVENT_TYPES = {
    "step_started",
    "tool_started",
    "tool_finished",
    "content",
}


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[str] = Field(min_length=1)


def make_usage(prompt_tokens: int, completion_tokens: int) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def make_registry(executed: list[list[str]]) -> ToolRegistry:
    async def search_handler(
        args: SearchArgs,
        context: ToolContext,
    ) -> dict[str, Any]:
        executed.append(list(args.requirements))
        return {
            "matches": [
                {
                    "requirement": requirement,
                    "status": "strong_match",
                    "evidence_ids": [101],
                }
                for requirement in args.requirements
            ]
        }

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="search_resume_evidence",
            description="双版本对比测试工具。",
            args_model=SearchArgs,
            handler=search_handler,
        )
    )
    return registry


def make_responses() -> list[LLMWithToolsResult]:
    return [
        LLMWithToolsResult(
            content=None,
            tool_calls=[
                ToolCall(
                    id="compare-call-1",
                    name="search_resume_evidence",
                    arguments='{"requirements": ["Python", "FastAPI"]}',
                )
            ],
            usage=make_usage(10, 3),
            latency_ms=5,
        ),
        LLMWithToolsResult(
            content="匹配分析完成",
            tool_calls=[],
            usage=make_usage(20, 4),
            latency_ms=5,
        ),
    ]


def make_chat_sequence(
    registry: ToolRegistry,
    responses: list[LLMWithToolsResult],
):
    queue = list(responses)

    async def chat_with_tools(messages, tools):
        assert tools == registry.openai_definitions()
        return queue.pop(0)

    return chat_with_tools


def make_context_factory(event_sink):
    def factory(state: dict, step: int) -> ToolContext:
        return ToolContext(
            current_user=CurrentUser(
                id=7,
                username="compare_user",
                role="admin",
            ),
            task_id=state.get("task_id"),
            step_no=step,
            event_sink=event_sink,
            collect_tool_audit=True,
            defer_report_save=True,
        )

    return factory


def make_event_sink(events: list[AgentEvent]):
    async def sink(event: AgentEvent) -> None:
        events.append(event)

    return sink


async def run_manual(
    *,
    registry: ToolRegistry,
    events: list[AgentEvent],
):
    manual_context = ToolContext(
        current_user=CurrentUser(
            id=7,
            username="compare_user",
            role="admin",
        ),
        collect_tool_audit=True,
        event_sink=make_event_sink(events),
    )
    react_agent.chat_with_tools = make_chat_sequence(
        registry,
        make_responses(),
    )
    return await run_react_loop(
        messages=build_jobfit_react_messages(
            job_description="需要 Python 和 FastAPI。",
            resume_text="使用 Python 开发 FastAPI 服务。",
            system_prompt=JOBFIT_REACT_SYSTEM_PROMPT,
        ),
        registry=registry,
        context=manual_context,
        max_steps=8,
        event_sink=make_event_sink(events),
    )


async def run_graph(
    *,
    registry: ToolRegistry,
    events: list[AgentEvent],
):
    graph = build_jobfit_graph(checkpointer=InMemorySaver())
    context: JobFitGraphContext = {
        "chat_with_tools": make_chat_sequence(
            registry,
            make_responses(),
        ),
        "tool_registry": registry,
        "tool_context_factory": make_context_factory(
            make_event_sink(events)
        ),
        "event_sink": make_event_sink(events),
    }
    state = {
        "task_id": 1,
        "job_id": 2,
        "resume_version_id": 3,
        "job_description": "需要 Python 和 FastAPI。",
        "resume_text": "使用 Python 开发 FastAPI 服务。",
        "system_prompt": JOBFIT_REACT_SYSTEM_PROMPT,
        "max_steps": 8,
        "trace": [],
    }
    config = {"configurable": {"thread_id": "compare-thread"}}
    first = await graph.ainvoke(
        state,
        config=config,
        context=context,
    )
    assert "__interrupt__" in first
    return await graph.ainvoke(
        Command(resume={"decision": "approve"}),
        config=config,
        context=context,
    )


async def main() -> None:
    manual_events: list[AgentEvent] = []
    graph_events: list[AgentEvent] = []
    executed: list[list[str]] = []
    registry = make_registry(executed)

    manual_result = await run_manual(
        registry=registry,
        events=manual_events,
    )
    graph_result = await run_graph(
        registry=registry,
        events=graph_events,
    )

    manual_core_events = [
        event.type
        for event in manual_events
        if event.type in CORE_EVENT_TYPES
    ]
    graph_core_events = [
        event.type
        for event in graph_events
        if event.type in CORE_EVENT_TYPES
    ]

    comparison = {
        "answer_equal": (
            manual_result.answer == graph_result["final_answer"]
        ),
        "status_equal": (
            manual_result.status == graph_result["react_status"]
        ),
        "steps_equal": (
            manual_result.steps == graph_result["current_step"]
        ),
        "usage_equal": (
            manual_result.usage.model_dump() == graph_result["usage"]
        ),
        "tool_trace_equal": [
            item.model_dump(mode="json")
            for item in manual_result.trace
        ]
        == graph_result["tool_trace"],
        "core_events_equal": manual_core_events == graph_core_events,
        "executed_tools_equal": executed
        == [
            ["Python", "FastAPI"],
            ["Python", "FastAPI"],
        ],
        "manual": {
            "answer": manual_result.answer,
            "status": manual_result.status,
            "steps": manual_result.steps,
            "usage": manual_result.usage.model_dump(),
            "core_events": manual_core_events,
        },
        "langgraph": {
            "answer": graph_result["final_answer"],
            "status": graph_result["react_status"],
            "steps": graph_result["current_step"],
            "usage": graph_result["usage"],
            "core_events": graph_core_events,
            "all_event_types": [
                event.type for event in graph_events
            ],
        },
    }

    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
