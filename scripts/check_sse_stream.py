# 使用真实 PostgreSQL、Redis 和模拟模型验证 SSE 完整链路。

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.cache.client import dispose_redis
from app.db.models import (
    AnalysisTask,
    Conversation,
    Job,
    KnowledgeChunk,
    Message,
    Report,
    Resume,
    ResumeVersion,
)
from app.db.session import async_session_factory, dispose_engine
from app.main import app
from app.repositories import (
    AnalysisTaskRepository,
    ConversationRepository,
    JobRepository,
    MessageRepository,
    ReportRepository,
    ResumeRepository,
    ResumeVersionRepository,
    ToolCallRecordRepository,
)
from app.schemas.chat import LLMWithToolsResult, TokenUsage, ToolCall
from app.schemas.extraction import JobExtraction
from app.services import react_agent
from app.services.persisted_agent import create_persisted_task
from app.services.rag_runtime import get_vector_index
from app.tools import jobfit


def parse_sse_events(body: str) -> list[dict]:
    events = []
    for block in body.strip().split("\n\n"):
        event_type = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_type = line.removeprefix("event: ")
            elif line.startswith("data: "):
                raw = line.removeprefix("data: ")
                data = raw if raw == "[DONE]" else json.loads(raw)
        if event_type is not None:
            events.append({"event": event_type, "data": data})
    return events


async def cleanup_data(
    *,
    task_id: int | None,
    conversation_id: int | None,
    job_id: int | None,
    resume_id: int | None,
    resume_version_id: int | None,
) -> None:
    async with async_session_factory() as session:
        async with session.begin():
            if task_id is not None:
                await session.execute(
                    delete(Report).where(Report.task_id == task_id)
                )
                await session.execute(
                    delete(AnalysisTask).where(
                        AnalysisTask.task_id == task_id
                    )
                )
            if conversation_id is not None:
                await session.execute(
                    delete(Message).where(
                        Message.conversation_id == conversation_id
                    )
                )
                await session.execute(
                    delete(Conversation).where(
                        Conversation.conversation_id == conversation_id
                    )
                )
            if job_id is not None:
                await session.execute(
                    delete(Job).where(Job.job_id == job_id)
                )
            if resume_version_id is not None:
                await session.execute(
                    delete(KnowledgeChunk).where(
                        KnowledgeChunk.resume_version_id
                        == resume_version_id
                    )
                )
            if resume_id is not None:
                await session.execute(
                    delete(ResumeVersion).where(
                        ResumeVersion.resume_id == resume_id
                    )
                )
                await session.execute(
                    delete(Resume).where(Resume.resume_id == resume_id)
                )

    if resume_version_id is not None:
        await asyncio.to_thread(
            get_vector_index().delete_resume_version,
            user_id=1,
            resume_version_id=resume_version_id,
        )

async def check_sse_stream() -> None:
    suffix = uuid4().hex
    previous_content = f"Previous question {suffix}"
    final_answer = f"Streaming analysis complete {suffix}"
    task_id = None
    conversation_id = None
    job_id = None
    resume_id = None
    resume_version_id = None
    captured_messages = []

    async with async_session_factory() as session:
        async with session.begin():
            resume = await ResumeRepository(session).create(
                user_id=1,
                title=f"SSE Resume {suffix}",
            )
            resume_id = resume.resume_id
            resume_version = await ResumeVersionRepository(
                session
            ).create_for_user(
                resume_id=resume.resume_id,
                user_id=1,
                version_no=1,
                raw_text="Python FastAPI PostgreSQL Docker",
                extracted_sections={
                    "sections": [
                        {
                            "section_type": "skills",
                            "title": "技能",
                            "content": "Python、FastAPI、PostgreSQL、Docker",
                        }
                    ]
                },
            )
            resume_version_id = resume_version.resume_version_id
            job = await JobRepository(session).create(
                user_id=1,
                title=f"SSE Job {suffix}",
                raw_description="Python FastAPI backend engineer",
            )
            job_id = job.job_id
            conversation = await ConversationRepository(session).create(
                user_id=1,
                title=f"SSE Conversation {suffix}",
            )
            conversation_id = conversation.conversation_id
            await MessageRepository(session).create_for_user(
                conversation_id=conversation.conversation_id,
                user_id=1,
                role="user",
                content=previous_content,
            )
            task = await create_persisted_task(
                session,
                user_id=1,
                job_id=job.job_id,
                resume_version_id=resume_version.resume_version_id,
                conversation_id=conversation.conversation_id,
            )
            task_id = task.task_id

    call_count = 0

    def last_tool_result(messages):
        for message in reversed(messages):
            if message.get("role") != "tool":
                continue

            payload = json.loads(message["content"])
            if payload.get("ok"):
                return payload["result"]

        raise RuntimeError("未找到上一轮工具结果")

    async def fake_chat_with_tools(*, messages, tools):
        nonlocal call_count
        call_count += 1
        captured_messages.append(messages)

        if call_count == 1:
            tool_call = ToolCall(
                id="sse-profile",
                name="get_resume_profile",
                arguments="{}",
            )
        elif call_count == 2:
            tool_call = ToolCall(
                id="sse-job",
                name="extract_job_requirements",
                arguments=json.dumps(
                    {
                        "job_description": (
                            "Python FastAPI backend engineer"
                        )
                    }
                ),
            )
        elif call_count == 3:
            tool_call = ToolCall(
                id="sse-search",
                name="search_resume_evidence",
                arguments=json.dumps(
                    {"requirements": ["熟悉 Python 和 FastAPI"]}
                ),
            )
        elif call_count == 4:
            tool_call = ToolCall(
                id="sse-assess",
                name="assess_requirement_match",
                arguments=json.dumps(last_tool_result(messages)),
            )
        elif call_count == 5:
            assessment = last_tool_result(messages)
            tool_call = ToolCall(
                id="sse-report",
                name="save_match_report",
                arguments=json.dumps(
                    {
                        "summary": "SSE report",
                        "result_json": assessment,
                    }
                ),
            )
        else:
            return LLMWithToolsResult(
                content=final_answer,
                tool_calls=[],
                usage=TokenUsage(
                    prompt_tokens=15,
                    completion_tokens=5,
                    total_tokens=20,
                ),
                latency_ms=7,
            )

        return LLMWithToolsResult(
            content=None,
            tool_calls=[tool_call],
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=2,
                total_tokens=12,
            ),
            latency_ms=5,
        )
    original_extract_job = jobfit.extract_job

    async def fake_extract_job(job_description):
        return JobExtraction(
            responsibilities=["负责 Python FastAPI 后端开发"],
            required_skills=["熟悉 Python 和 FastAPI"],
            nice_to_have=[],
        )

    jobfit.extract_job = fake_extract_job

    original_chat_with_tools = react_agent.chat_with_tools
    react_agent.chat_with_tools = fake_chat_with_tools

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            async with client.stream(
                "GET",
                f"/api/agent/tasks/{task_id}/stream",
                headers={"Authorization": "Bearer demo-token"},
            ) as response:
                body = (await response.aread()).decode()
                assert response.status_code == 200
                assert response.headers["content-type"].startswith(
                    "text/event-stream"
                )

        events = parse_sse_events(body)
        event_types = [item["event"] for item in events]
        assert event_types[0] == "task_started"
        assert "step_started" in event_types
        assert "tool_started" in event_types
        assert "tool_finished" in event_types
        assert "index_started" in event_types
        assert "index_finished" in event_types
        assert "retrieval_started" in event_types
        assert "retrieval_finished" in event_types
        assert "content" in event_types
        assert "task_completed" in event_types
        assert event_types[-1] == "done"
        print("sse_event_order_ok")

        assert captured_messages
        assert "<会话历史>" in captured_messages[0][1]["content"]
        assert previous_content in captured_messages[0][1]["content"]
        print("conversation_context_ok")

        async with async_session_factory() as session:
            task = await AnalysisTaskRepository(session).get_for_user(
                task_id=task_id,
                user_id=1,
            )
            report = await ReportRepository(session).get_current_for_user(
                task_id=task_id,
                user_id=1,
            )
            records = await ToolCallRecordRepository(session).list_for_user(
                task_id=task_id,
                user_id=1,
            )
            messages = await MessageRepository(session).list_for_user(
                conversation_id=conversation_id,
                user_id=1,
            )

        assert task is not None and task.status == "completed"
        assert report is not None and report.is_current is True
        assert "chunk_id" in json.dumps(
            report.result_json,
            ensure_ascii=False,
        )
        assert {record.tool_name for record in records} >= {
            "get_resume_profile",
            "extract_job_requirements",
            "search_resume_evidence",
            "assess_requirement_match",
            "save_match_report",
        }
        assert len(messages) == 2
        assert messages[-1].role == "assistant"
        assert messages[-1].content == final_answer
        print("sse_persistence_ok")
    finally:
        react_agent.chat_with_tools = original_chat_with_tools
        jobfit.extract_job = original_extract_job
        try:
            await cleanup_data(
                task_id=task_id,
                conversation_id=conversation_id,
                job_id=job_id,
                resume_id=resume_id,
                resume_version_id=resume_version_id,
            )
        finally:
            await dispose_redis()
            await dispose_engine()
        print("sse_cleanup_ok")


if __name__ == "__main__":
    asyncio.run(check_sse_stream())
