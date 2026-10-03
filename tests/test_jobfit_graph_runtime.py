# 验证 JobFit Graph 与手写 ReAct 的核心行为契约一致。

import asyncio
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.graphs.jobfit import JobFitGraphContext, build_jobfit_graph
from app.schemas.agent_events import AgentEvent
from app.schemas.auth import CurrentUser
from app.schemas.chat import LLMWithToolsResult, TokenUsage, ToolCall
from app.services import react_agent as react_agent_module
from app.services.react_agent import (
    JOBFIT_REACT_SYSTEM_PROMPT,
    build_jobfit_react_messages,
    run_react_loop,
)
from app.tools import ToolContext, ToolRegistry, ToolSpec


class SearchEvidenceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[str] = Field(min_length=1)


def make_usage(
    prompt_tokens: int,
    completion_tokens: int,
) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def make_registry(executed: list[list[str]]) -> ToolRegistry:
    async def search_handler(
        args: SearchEvidenceArgs,
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
            description="测试用证据检索工具。",
            args_model=SearchEvidenceArgs,
            handler=search_handler,
        )
    )
    return registry


def make_context(
    *,
    event_sink,
) -> ToolContext:
    return ToolContext(
        current_user=CurrentUser(
            id=7,
            username="test_user",
            role="admin",
        ),
        task_id=1,
        step_no=1,
        event_sink=event_sink,
        defer_report_save=True,
        collect_tool_audit=True,
    )


def make_context_factory(*, event_sink):
    def factory(state: dict, step: int) -> ToolContext:
        context = make_context(event_sink=event_sink)
        context.task_id = state.get("task_id")
        context.step_no = step
        return context

    return factory


def make_tool_call(
    call_id: str,
    requirements: list[str],
) -> ToolCall:
    return ToolCall(
        id=call_id,
        name="search_resume_evidence",
        arguments=json.dumps(
            {"requirements": requirements},
            ensure_ascii=False,
        ),
    )


def make_chat_sequence(
    *,
    responses: list[LLMWithToolsResult],
    registry: ToolRegistry,
    captured_messages: list[list[dict[str, Any]]] | None = None,
):
    queue = list(responses)

    async def chat_with_tools(
        messages: list[dict[str, Any]],
        tools: list[dict],
    ) -> LLMWithToolsResult:
        if captured_messages is not None:
            captured_messages.append([*messages])
        assert tools == registry.openai_definitions()
        return queue.pop(0)

    return chat_with_tools


def make_event_sink(events: list[AgentEvent]):
    async def sink(event: AgentEvent) -> None:
        events.append(event)

    return sink


def make_initial_state(**overrides) -> dict:
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
    state.update(overrides)
    return state


def test_graph_matches_handwritten_react_contract(monkeypatch) -> None:
    registry = make_registry(executed=[])
    manual_events: list[AgentEvent] = []
    graph_events: list[AgentEvent] = []
    manual_context = make_context(event_sink=make_event_sink(manual_events))

    manual_chat = make_chat_sequence(
        registry=registry,
        responses=[
            LLMWithToolsResult(
                content=None,
                tool_calls=[
                    make_tool_call("call-1", ["Python", "FastAPI"])
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
        ],
    )
    monkeypatch.setattr(
        react_agent_module,
        "chat_with_tools",
        manual_chat,
    )

    manual_result = asyncio.run(
        run_react_loop(
            messages=build_jobfit_react_messages(
                job_description="需要 Python 和 FastAPI。",
                resume_text="使用 Python 开发 FastAPI 服务。",
                system_prompt=JOBFIT_REACT_SYSTEM_PROMPT,
            ),
            registry=registry,
            context=manual_context,
            max_steps=8,
            event_sink=make_event_sink(manual_events),
        )
    )

    graph = build_jobfit_graph()
    graph_chat = make_chat_sequence(
        registry=registry,
        responses=[
            LLMWithToolsResult(
                content=None,
                tool_calls=[
                    make_tool_call("call-1", ["Python", "FastAPI"])
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
        ],
    )
    graph_context: JobFitGraphContext = {
        "chat_with_tools": graph_chat,
        "tool_registry": registry,
        "tool_context_factory": make_context_factory(
            event_sink=make_event_sink(graph_events)
        ),
        "event_sink": make_event_sink(graph_events),
    }

    graph_result = asyncio.run(
        graph.ainvoke(
            make_initial_state(),
            context=graph_context,
        )
    )

    assert manual_result.answer == graph_result["final_answer"]
    assert manual_result.status == graph_result["react_status"]
    assert manual_result.steps == graph_result["current_step"]
    assert manual_result.usage.model_dump() == graph_result["usage"]
    assert [
        item.model_dump(mode="json")
        for item in manual_result.trace
    ] == graph_result["tool_trace"]
    assert [
        item.model_dump(mode="json")
        for item in manual_context.tool_audit_events
    ] == graph_result["tool_audit_events"]
    assert [event.type for event in manual_events] == [
        event.type for event in graph_events
    ]
    assert [
        message["role"]
        for message in graph_result["messages"]
    ] == ["system", "user", "assistant", "tool"]


def test_graph_matches_max_steps_contract(monkeypatch) -> None:
    registry = make_registry(executed=[])
    manual_chat = make_chat_sequence(
        registry=registry,
        responses=[
            LLMWithToolsResult(
                content=None,
                tool_calls=[
                    make_tool_call("call-1", ["Python"])
                ],
                usage=make_usage(10, 3),
                latency_ms=5,
            )
        ],
    )
    monkeypatch.setattr(
        react_agent_module,
        "chat_with_tools",
        manual_chat,
    )

    manual_result = asyncio.run(
        run_react_loop(
            messages=build_jobfit_react_messages(
                job_description="需要 Python。",
                resume_text="使用 Python。",
                system_prompt=JOBFIT_REACT_SYSTEM_PROMPT,
            ),
            registry=registry,
            context=make_context(event_sink=None),
            max_steps=1,
        )
    )

    graph = build_jobfit_graph()
    graph_context: JobFitGraphContext = {
        "chat_with_tools": make_chat_sequence(
            registry=registry,
            responses=[
                LLMWithToolsResult(
                    content=None,
                    tool_calls=[
                        make_tool_call("call-1", ["Python"])
                    ],
                    usage=make_usage(10, 3),
                    latency_ms=5,
                )
            ],
        ),
        "tool_registry": registry,
        "tool_context_factory": make_context_factory(event_sink=None),
        "event_sink": None,
    }

    graph_result = asyncio.run(
        graph.ainvoke(
            make_initial_state(max_steps=1),
            context=graph_context,
        )
    )

    assert manual_result.status == "max_steps_reached"
    assert graph_result["react_status"] == "max_steps_reached"
    assert manual_result.steps == graph_result["current_step"] == 1
    assert manual_result.answer is None
    assert graph_result["final_answer"] is None
    assert graph_result["tool_trace"][0]["tool_name"] == (
        "search_resume_evidence"
    )


def test_graph_rejects_without_saving_report() -> None:
    registry = make_registry(executed=[])
    graph = build_jobfit_graph()
    context: JobFitGraphContext = {
        "chat_with_tools": make_chat_sequence(
            registry=registry,
            responses=[
                LLMWithToolsResult(
                    content="等待用户确认",
                    tool_calls=[],
                    usage=make_usage(10, 2),
                    latency_ms=5,
                )
            ],
        ),
        "tool_registry": registry,
        "tool_context_factory": make_context_factory(event_sink=None),
        "event_sink": None,
    }

    result = asyncio.run(
        graph.ainvoke(
            make_initial_state(confirmation_decision="reject"),
            context=context,
        )
    )

    assert result["status"] == "cancelled"
    assert result["error_code"] == "user_rejected"
    assert result.get("report_id") is None
    assert result["trace"][-1] == "cancel"


def test_prepare_run_validates_required_identifiers() -> None:
    from app.graphs.jobfit.nodes import prepare_run
    import pytest

    with pytest.raises(ValueError):
        prepare_run(
            {
                "task_id": 0,
                "job_id": 2,
                "resume_version_id": 3,
                "max_steps": 8,
            }
        )



def test_graph_executes_real_rag_tool_and_preserves_evidence_pack(
    monkeypatch,
) -> None:
    from app.schemas.evidence import (
        EvidenceItem as SearchEvidenceItem,
        EvidenceSearchResult,
        RequirementEvidence,
    )
    from app.schemas.knowledge import (
        EvidenceItem as KnowledgeEvidenceItem,
        EvidencePack,
    )
    import app.tools.jobfit as jobfit_module
    from app.tools.jobfit import build_jobfit_tool_registry

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    evidence_pack = EvidencePack(
        requirement="Python",
        items=[
            KnowledgeEvidenceItem(
                chunk_id=101,
                user_id=7,
                resume_version_id=3,
                section_type="skills",
                title="技能",
                content="Python",
                content_hash="a" * 64,
                position=1,
                chunker_version="v1",
                relevance_score=0.9,
                rank=1,
            )
        ],
        rerank_applied=True,
    )
    search_result = EvidenceSearchResult(
        requirements=["Python"],
        matches=[
            RequirementEvidence(
                requirement="Python",
                evidence=[
                    SearchEvidenceItem(
                        section_type="skills",
                        title="技能",
                        content="Python",
                        score=0.9,
                        chunk_id=101,
                        source_version_id=3,
                        position=1,
                    )
                ],
            )
        ],
    )

    async def fake_search_requirements_with_rag(
        session,
        *,
        user_id: int,
        resume_version_id: int,
        requirements: list[str],
    ):
        assert user_id == 7
        assert resume_version_id == 3
        assert requirements == ["Python"]
        return search_result, [evidence_pack]

    monkeypatch.setattr(
        jobfit_module,
        "search_requirements_with_rag",
        fake_search_requirements_with_rag,
    )

    registry = build_jobfit_tool_registry()

    def context_factory(state: dict, step: int) -> ToolContext:
        return ToolContext(
            current_user=CurrentUser(
                id=7,
                username="test_user",
                role="admin",
            ),
            task_id=state.get("task_id"),
            step_no=step,
            session_factory=FakeSessionContext,
            resume_version_id=3,
            rag_enabled=True,
            defer_report_save=True,
            collect_tool_audit=True,
        )

    graph = build_jobfit_graph()
    context: JobFitGraphContext = {
        "chat_with_tools": make_chat_sequence(
            registry=registry,
            responses=[
                LLMWithToolsResult(
                    content=None,
                    tool_calls=[
                        make_tool_call("call-rag-1", ["Python"])
                    ],
                    usage=make_usage(10, 3),
                    latency_ms=5,
                ),
                LLMWithToolsResult(
                    content="RAG 分析完成",
                    tool_calls=[],
                    usage=make_usage(20, 4),
                    latency_ms=5,
                ),
            ],
        ),
        "tool_registry": registry,
        "tool_context_factory": context_factory,
        "event_sink": None,
    }

    result = asyncio.run(
        graph.ainvoke(
            make_initial_state(),
            context=context,
        )
    )

    assert result["final_answer"] == "RAG 分析完成"
    assert result["retrieved_evidence_packs"][0]["requirement"] == "Python"
    assert result["retrieved_evidence_packs"][0]["items"][0][
        "chunk_id"
    ] == 101
