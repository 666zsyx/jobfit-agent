# 使用真实模型验收 STEP 07 持久化 Agent 和工具审计。

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.exceptions import LLMServiceError
from app.db.models import AnalysisTask, Job, Report, Resume, ResumeVersion, User
from app.db.session import async_session_factory, dispose_engine
from app.repositories import (
    AnalysisTaskRepository,
    JobRepository,
    ReportRepository,
    ResumeRepository,
    ResumeVersionRepository,
    ToolCallRecordRepository,
)
from app.services.persisted_agent import (
    create_persisted_task,
    run_persisted_task,
)


async def cleanup_test_data(usernames: list[str]) -> None:
    async with async_session_factory() as session:
        async with session.begin():
            user_ids = select(User.user_id).where(
                User.username.in_(usernames)
            )
            task_ids = select(AnalysisTask.task_id).where(
                AnalysisTask.user_id.in_(user_ids)
            )
            resume_ids = select(Resume.resume_id).where(
                Resume.user_id.in_(user_ids)
            )
            await session.execute(
                delete(Report).where(Report.task_id.in_(task_ids))
            )
            await session.execute(
                delete(AnalysisTask).where(
                    AnalysisTask.user_id.in_(user_ids)
                )
            )
            await session.execute(
                delete(ResumeVersion).where(
                    ResumeVersion.resume_id.in_(resume_ids)
                )
            )
            await session.execute(
                delete(Resume).where(Resume.user_id.in_(user_ids))
            )
            await session.execute(
                delete(Job).where(Job.user_id.in_(user_ids))
            )
            await session.execute(
                delete(User).where(User.user_id.in_(user_ids))
            )

async def verify_step07_persisted_agent() -> None:
    suffix = uuid4().hex
    username = f"verify_step07_{suffix}"
    resume_text = (
        "掌握 Python 和 FastAPI，完成过异步 API 与 SQLAlchemy 项目。"
        "具备 PostgreSQL、React 和 Docker 基础。"
    )
    job_description = (
        "招聘 Python 后端开发实习生，要求熟悉 FastAPI、PostgreSQL，"
        "了解 Agent 应用、RAG 和 Docker。"
    )

    try:
        async with async_session_factory() as session:
            async with session.begin():
                user = User(
                    username=username,
                    email=f"{username}@example.com",
                    role="user",
                )
                session.add(user)
                await session.flush()

                resume = await ResumeRepository(session).create(
                    user_id=user.user_id,
                    title="STEP 07 真实验收简历",
                )
                resume_version = await ResumeVersionRepository(
                    session
                ).create_for_user(
                    resume_id=resume.resume_id,
                    user_id=user.user_id,
                    version_no=1,
                    raw_text=resume_text,
                )
                job = await JobRepository(session).create(
                    user_id=user.user_id,
                    raw_description=job_description,
                    title="Python 后端开发实习生",
                )
                task = await create_persisted_task(
                    session,
                    user_id=user.user_id,
                    job_id=job.job_id,
                    resume_version_id=resume_version.resume_version_id,
                    conversation_id=None,
                )
                user_id = user.user_id
                task_id = task.task_id

        result = None
        last_interruption = None

        for run_number in range(2):
            try:
                result = await run_persisted_task(
                    async_session_factory,
                    user_id=user_id,
                    task_id=task_id,
                )
            except LLMServiceError as exc:
                last_interruption = str(exc)
                if run_number == 1:
                    raise
                continue

            if result.status == "interrupted":
                last_interruption = result.answer or "task_interrupted"
                if run_number == 1:
                    raise RuntimeError(
                        f"真实模型连续中断: {last_interruption}"
                    )
                continue

            break

        if result is None or result.status != "completed":
            raise RuntimeError(
                f"真实模型验收失败: {last_interruption}"
            )

        async with async_session_factory() as session:
            task = await AnalysisTaskRepository(session).get_for_user(
                task_id=task_id,
                user_id=user_id,
            )
            report = await ReportRepository(session).get_current_for_user(
                task_id=task_id,
                user_id=user_id,
            )
            tool_records = await ToolCallRecordRepository(
                session
            ).list_for_user(
                task_id=task_id,
                user_id=user_id,
            )

        if task is None or task.status != "completed":
            raise RuntimeError("任务未进入 completed")

        if report is None:
            raise RuntimeError("当前报告不存在")

        json.dumps(report.result_json, ensure_ascii=False)

        print(f"task_id={task.task_id}")
        print(f"status={task.status}")
        print(f"attempt={task.attempt}")
        print(f"steps={result.steps}")
        print(f"report_version={report.version_no}")
        print(f"tool_record_count={len(tool_records)}")
        print(
            "tool_names="
            + ",".join(
                sorted({record.tool_name for record in tool_records})
            )
        )
        print(f"latency_ms={result.latency_ms}")
    finally:
        try:
            await cleanup_test_data([username])
        finally:
            await dispose_engine()


if __name__ == "__main__":
    asyncio.run(verify_step07_persisted_agent())