# 验证 JobFit Graph 的 PostgreSQL Checkpoint 写入和重新打开读取。

import asyncio
import json
import secrets
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from typing import Any

from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field

from app.core.event_loop import configure_event_loop_policy
from app.db.checkpoint import (
    build_checkpoint_config,
    checkpoint_thread_id,
    open_postgres_checkpointer,
)
from app.graphs.jobfit import JobFitGraphContext, build_jobfit_graph
from app.schemas.auth import CurrentUser
from app.schemas.chat import LLMWithToolsResult, TokenUsage, ToolCall
from app.services.react_agent import JOBFIT_REACT_SYSTEM_PROMPT
from app.tools import ToolContext, ToolRegistry, ToolSpec

configure_event_loop_policy()


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[str] = Field(min_length=1)


def make_usage(prompt_tokens: int, completion_tokens: int) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def make_registry() -> ToolRegistry:
    async def search_handler(
        args: SearchArgs,
        context: ToolContext,
    ) -> dict[str, Any]:
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
            description="Checkpoint 验证工具。",
            args_model=SearchArgs,
            handler=search_handler,
        )
    )
    return registry


def make_chat(registry: ToolRegistry):
    responses = [
        LLMWithToolsResult(
            content=None,
            tool_calls=[
                ToolCall(
                    id="checkpoint-call-1",
                    name="search_resume_evidence",
                    arguments=json.dumps(
                        {"requirements": ["Python"]},
                        ensure_ascii=False,
                    ),
                )
            ],
            usage=make_usage(10, 3),
            latency_ms=5,
        ),
        LLMWithToolsResult(
            content="Checkpoint 验证完成",
            tool_calls=[],
            usage=make_usage(20, 4),
            latency_ms=5,
        ),
    ]
    queue = list(responses)

    async def chat_with_tools(messages, tools):
        assert tools == registry.openai_definitions()
        return queue.pop(0)

    return chat_with_tools


def make_context_factory():
    def factory(state: dict, step: int) -> ToolContext:
        return ToolContext(
            current_user=CurrentUser(
                id=7,
                username="checkpoint_user",
                role="admin",
            ),
            task_id=state.get("task_id"),
            step_no=step,
            collect_tool_audit=True,
            defer_report_save=True,
        )

    return factory


async def main() -> None:
    task_id = secrets.randbelow(1_000_000_000) + 1
    thread_id = checkpoint_thread_id(task_id)
    config = build_checkpoint_config(task_id)
    registry = make_registry()
    runtime_context: JobFitGraphContext = {
        "chat_with_tools": make_chat(registry),
        "tool_registry": registry,
        "tool_context_factory": make_context_factory(),
        "event_sink": None,
    }
    initial_state = {
        "task_id": task_id,
        "job_id": 2,
        "resume_version_id": 3,
        "job_description": "需要 Python 开发经验。",
        "resume_text": "使用 Python 完成多个服务开发。",
        "system_prompt": JOBFIT_REACT_SYSTEM_PROMPT,
        "max_steps": 8,
        "trace": [],
    }

    async with open_postgres_checkpointer(setup=True) as saver:
        graph = build_jobfit_graph(checkpointer=saver)
        interrupted_result = await graph.ainvoke(
            initial_state,
            config=config,
            context=runtime_context,
        )

    assert "__interrupt__" in interrupted_result
    assert interrupted_result["pending_report"]["summary"]

    edited_report = {
        "summary": "修改后的 Checkpoint 报告",
        "result_json": {"answer": "修改后的结论", "chunk_ids": [101]},
    }

    async with open_postgres_checkpointer() as saver:
        graph = build_jobfit_graph(checkpointer=saver)
        waiting_snapshot = await graph.aget_state(config)
        resumed_result = await graph.ainvoke(
            Command(
                resume={
                    "decision": "revise",
                    "edited_report": edited_report,
                    "resume_revision_text": "修改后的简历版本",
                }
            ),
            config=config,
            context=runtime_context,
        )
        final_snapshot = await graph.aget_state(config)
        await saver.adelete_thread(thread_id)

    assert list(waiting_snapshot.next) == ["human_confirmation"]
    assert resumed_result["status"] == "completed"
    assert resumed_result["confirmation_decision"] == "revise"
    assert resumed_result["reviewed_report"] == edited_report
    assert resumed_result["resume_revision_text"] == "修改后的简历版本"
    assert final_snapshot.next == ()

    print(
        json.dumps(
            {
                "task_id": task_id,
                "thread_id": thread_id,
                "interrupted": "__interrupt__" in interrupted_result,
                "waiting_node": list(waiting_snapshot.next),
                "resume_decision": resumed_result[
                    "confirmation_decision"
                ],
                "reviewed_summary": resumed_result[
                    "reviewed_report"
                ]["summary"],
                "resume_revision_text": resumed_result[
                    "resume_revision_text"
                ],
                "status": resumed_result["status"],
                "checkpoint_reopened": True,
                "checkpoint_next": list(final_snapshot.next),
                "cleanup_completed": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())



