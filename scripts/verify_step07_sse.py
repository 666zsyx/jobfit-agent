# 使用真实 DeepSeek、PostgreSQL 和 Redis 验证 Agent SSE 服务。

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import delete

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.cache.client import dispose_redis
from app.db.models import (
    AnalysisTask,
    Conversation,
    Job,
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
from app.services.persisted_agent import create_persisted_task


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
            if resume_id is not None:
                await session.execute(
                    delete(ResumeVersion).where(
                        ResumeVersion.resume_id == resume_id
                    )
                )
                await session.execute(
                    delete(Resume).where(Resume.resume_id == resume_id)
                )


async def read_stream(task_id: int) -> list[dict]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        timeout=120,
    ) as client:
        async with client.stream(
            "GET",
            f"/api/agent/tasks/{task_id}/stream",
            headers={"Authorization": "Bearer demo-token"},
        ) as response:
            assert response.status_code == 200
            body = (await response.aread()).decode()
    return parse_sse_events(body)


async def verify_step07_sse() -> None:
    suffix = uuid4().hex
    task_id = None
    conversation_id = None
    job_id = None
    resume_id = None

    try:
        async with async_session_factory() as session:
            async with session.begin():
                resume = await ResumeRepository(session).create(
                    user_id=1,
                    title=f"STEP07 SSE Resume {suffix}",
                )
                resume_id = resume.resume_id
                version = await ResumeVersionRepository(
                    session
                ).create_for_user(
                    resume_id=resume.resume_id,
                    user_id=1,
                    version_no=1,
                    raw_text=(
                        "Python FastAPI PostgreSQL Redis SQLAlchemy "
                        "RAG Agent Docker"
                    ),
                )
                job = await JobRepository(session).create(
                    user_id=1,
                    title=f"STEP07 SSE Job {suffix}",
                    raw_description=(
                        "招聘 Python 后端实习生，要求 FastAPI、"
                        "PostgreSQL、Redis、RAG 和 Agent 基础。"
                    ),
                )
                job_id = job.job_id
                conversation = await ConversationRepository(session).create(
                    user_id=1,
                    title=f"STEP07 SSE Conversation {suffix}",
                )
                conversation_id = conversation.conversation_id
                await MessageRepository(session).create_for_user(
                    conversation_id=conversation.conversation_id,
                    user_id=1,
                    role="user",
                    content="请给出带证据的岗位匹配分析。",
                )
                task = await create_persisted_task(
                    session,
                    user_id=1,
                    job_id=job.job_id,
                    resume_version_id=version.resume_version_id,
                    conversation_id=conversation.conversation_id,
                )
                task_id = task.task_id

        events = []
        for _ in range(2):
            events = await read_stream(task_id)
            event_types = [item["event"] for item in events]
            if "task_completed" in event_types:
                break
            if "task_interrupted" not in event_types:
                raise RuntimeError("真实 SSE 未返回终态事件")
        else:
            raise RuntimeError("真实 SSE 连续中断")

        event_types = [item["event"] for item in events]
        assert event_types[0] == "task_started"
        assert "tool_started" in event_types
        assert "tool_finished" in event_types
        assert event_types[-1] == "done"

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
        assert records
        assert len(messages) >= 2
        assert messages[-1].role == "assistant"

        print("sse_real_status=completed")
        print(f"sse_real_report_version={report.version_no}")
        print(f"sse_real_tool_record_count={len(records)}")
        print(
            "sse_real_tools="
            + ",".join(sorted({record.tool_name for record in records}))
        )
        print(f"sse_real_event_count={len(events)}")
    finally:
        try:
            await cleanup_data(
                task_id=task_id,
                conversation_id=conversation_id,
                job_id=job_id,
                resume_id=resume_id,
            )
        finally:
            await dispose_redis()
            await dispose_engine()


if __name__ == "__main__":
    asyncio.run(verify_step07_sse())
