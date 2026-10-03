# 验证 LangGraph Agent 的持久化运行、人工确认和恢复。

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.event_loop import configure_event_loop_policy
from app.core.observability import (
    reset_request_id,
    set_request_id,
)
from app.db.checkpoint import (
    checkpoint_thread_id,
    open_postgres_checkpointer,
)
from app.db.models import (
    AnalysisTask,
    Job,
    KnowledgeChunk,
    Report,
    Resume,
    ResumeVersion,
    ToolCallRecord,
    User,
)
from app.db.session import async_session_factory
from app.schemas.chat import LLMWithToolsResult, TokenUsage, ToolCall
from app.services import graph_agent
from app.services.analysis_tasks import create_analysis_task
from app.tools import ToolRegistry, ToolSpec
from app.services.graph_agent import (
    resume_graph_persisted_task,
    run_graph_persisted_task,
)

configure_event_loop_policy()


async def cleanup_resources(
    *,
    user_id: int | None,
    task_id: int | None,
) -> None:
    if user_id is None:
        return

    async with async_session_factory() as session:
        async with session.begin():
            if task_id is not None:
                await session.execute(
                    delete(Report).where(Report.task_id == task_id)
                )
                await session.execute(
                    delete(ToolCallRecord).where(
                        ToolCallRecord.task_id == task_id
                    )
                )
                await session.execute(
                    delete(AnalysisTask).where(
                        AnalysisTask.task_id == task_id
                    )
                )
            resume_ids = select(Resume.resume_id).where(
                Resume.user_id == user_id
            )
            await session.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.user_id == user_id
                )
            )
            await session.execute(
                delete(ResumeVersion).where(
                    ResumeVersion.resume_id.in_(resume_ids)
                )
            )
            await session.execute(
                delete(Resume).where(Resume.user_id == user_id)
            )
            await session.execute(
                delete(Job).where(Job.user_id == user_id)
            )
            await session.execute(
                delete(User).where(User.user_id == user_id)
            )

    if task_id is not None:
        thread_id = checkpoint_thread_id(task_id, 1)
        async with open_postgres_checkpointer() as saver:
            await saver.adelete_thread(thread_id)


def make_usage() -> TokenUsage:
    return TokenUsage(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )



class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[str] = Field(min_length=1)


def make_registry() -> ToolRegistry:
    async def search_handler(args: SearchArgs, context):
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
            description="STEP 11 验证工具。",
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
                    id="step11-graph-call-1",
                    name="search_resume_evidence",
                    arguments='{"requirements": ["Python"]}',
                )
            ],
            usage=make_usage(),
            latency_ms=5,
        ),
        LLMWithToolsResult(
            content="审核前结论",
            tool_calls=[],
            usage=make_usage(),
            latency_ms=5,
        ),
    ]
    queue = list(responses)

    async def fake_chat_with_tools(messages, tools):
        assert tools == registry.openai_definitions()
        return queue.pop(0)

    return fake_chat_with_tools


async def main() -> None:
    user_id: int | None = None
    task_id: int | None = None
    request_id = f"step12-observability-{uuid4().hex[:12]}"
    request_token = set_request_id(request_id)

    try:
        suffix = uuid4().hex[:12]

        async with async_session_factory() as session:
            async with session.begin():
                user = User(
                    username=f"step11_{suffix}",
                    email=f"step11_{suffix}@example.com",
                    role="user",
                    status="active",
                )
                session.add(user)
                await session.flush()

                resume = Resume(
                    user_id=user.user_id,
                    title="STEP 11 Graph 验证简历",
                    status="active",
                )
                session.add(resume)
                await session.flush()

                resume_version = ResumeVersion(
                    resume_id=resume.resume_id,
                    version_no=1,
                    raw_text="使用 Python 开发 FastAPI 服务。",
                    extracted_sections=None,
                    source_type="text",
                )
                session.add(resume_version)

                job = Job(
                    user_id=user.user_id,
                    title="Python 后端实习生",
                    company_name="JobFit",
                    raw_description="需要 Python 和 FastAPI 开发经验。",
                    status="active",
                )
                session.add(job)
                await session.flush()

                task = await create_analysis_task(
                    session,
                    user_id=user.user_id,
                    job_id=job.job_id,
                    resume_version_id=resume_version.resume_version_id,
                    max_steps=8,
                )
                user_id = user.user_id
                task_id = task.task_id

        async def fake_prepare_rag(*args, **kwargs) -> bool:
            return False

        registry = make_registry()
        graph_agent._prepare_rag_safely = fake_prepare_rag
        graph_agent.build_jobfit_tool_registry = lambda: registry
        graph_agent.chat_with_tools = make_chat(registry)

        first_result = await run_graph_persisted_task(
            async_session_factory,
            user_id=user_id,
            task_id=task_id,
        )

        async with async_session_factory() as session:
            waiting_task = await session.scalar(
                select(AnalysisTask).where(
                    AnalysisTask.task_id == task_id
                )
            )

        assert first_result.status == "waiting_confirmation"
        assert first_result.interrupted is True
        assert first_result.pending_confirmation is not None
        assert waiting_task is not None
        assert waiting_task.status == "waiting_confirmation"
        assert waiting_task.current_node == "human_confirmation"

        edited_report = {
            "summary": "人工确认后的报告",
            "result_json": {"answer": "确认后结论", "chunk_ids": [101]},
        }
        second_result = await resume_graph_persisted_task(
            async_session_factory,
            user_id=user_id,
            task_id=task_id,
            decision="revise",
            edited_report=edited_report,
            resume_revision_text="修改后的简历文本",
        )

        async with async_session_factory() as session:
            completed_task = await session.scalar(
                select(AnalysisTask).where(
                    AnalysisTask.task_id == task_id
                )
            )
            report = await session.scalar(
                select(Report).where(Report.task_id == task_id)
            )
            tool_record_count = await session.scalar(
                select(func.count()).select_from(ToolCallRecord).where(
                    ToolCallRecord.task_id == task_id
                )
            )
            resume = await session.scalar(
                select(Resume).where(Resume.user_id == user_id)
            )
            versions = list(
                await session.scalars(
                    select(ResumeVersion)
                    .where(ResumeVersion.resume_id == resume.resume_id)
                    .order_by(ResumeVersion.version_no)
                )
            )

        assert second_result.status == "completed"
        assert second_result.report_id is not None
        assert second_result.new_resume_version_id is not None
        assert completed_task is not None
        assert completed_task.status == "completed"
        assert completed_task.current_node == "finalize"
        assert completed_task.last_request_id == request_id
        assert completed_task.metrics_json is not None
        assert completed_task.metrics_json["request_id"] == request_id
        assert completed_task.metrics_json["node_ms"] >= 0
        assert completed_task.metrics_json["steps"] >= 1
        assert report is not None
        assert report.summary == "人工确认后的报告"
        assert tool_record_count == 1
        assert len(versions) == 2
        assert versions[-1].raw_text == "修改后的简历文本"

        print(
            json.dumps(
                {
                    "task_id": task_id,
                    "waiting_status": first_result.status,
                    "waiting_node": first_result.current_node,
                    "resume_decision": "revise",
                    "final_status": second_result.status,
                    "report_id": second_result.report_id,
                    "report_summary": report.summary,
                    "new_resume_version_id": (
                        second_result.new_resume_version_id
                    ),
                    "resume_version_count": len(versions),
                    "request_id": request_id,
                    "metrics": completed_task.metrics_json,
                    "cleanup_completed": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        reset_request_id(request_token)
        await cleanup_resources(user_id=user_id, task_id=task_id)


if __name__ == "__main__":
    asyncio.run(main())
