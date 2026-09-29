# 使用模拟模型调用验证持久化 Agent 的完整任务链路。

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.exceptions import LLMServiceError, TaskStateConflictError
from app.db.models import AnalysisTask, Job, Report, Resume, ResumeVersion, User
from app.db.session import async_session_factory, dispose_engine
from app.repositories import (
    AnalysisTaskRepository,
    JobRepository,
    ReportRepository,
    ResumeRepository,
    ResumeVersionRepository,
)
from app.schemas.chat import LLMWithToolsResult, TokenUsage, ToolCall
from app.services import react_agent
from app.services.persisted_agent import (
    create_persisted_task,
    run_persisted_task,
)


def usage(prompt_tokens: int, completion_tokens: int) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
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


async def check_persisted_agent() -> None:
    suffix = uuid4().hex
    username1 = f"persisted_user1_{suffix}"
    username2 = f"persisted_user2_{suffix}"
    call_count = 0
    current_task_id: int | None = None

    async def fake_chat_with_tools(*, messages, tools):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            return LLMWithToolsResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call-profile",
                        name="get_resume_profile",
                        arguments="{}",
                    )
                ],
                usage=usage(10, 2),
                latency_ms=10,
            )

        if call_count == 2:
            return LLMWithToolsResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call-report",
                        name="save_match_report",
                        arguments=json.dumps(
                            {
                                "summary": "Persisted match report",
                                "result_json": {
                                    "matches": [
                                        {"status": "strong_match"}
                                    ]
                                },
                            },
                            ensure_ascii=False,
                        ),
                    )
                ],
                usage=usage(12, 3),
                latency_ms=11,
            )

        return LLMWithToolsResult(
            content="Persisted analysis completed.",
            tool_calls=[],
            usage=usage(20, 5),
            latency_ms=12,
        )

    original_chat_with_tools = react_agent.chat_with_tools
    react_agent.chat_with_tools = fake_chat_with_tools

    try:
        async with async_session_factory() as setup_session:
            async with setup_session.begin():
                resume_repository = ResumeRepository(setup_session)
                version_repository = ResumeVersionRepository(setup_session)
                job_repository = JobRepository(setup_session)

                user1 = User(
                    username=username1,
                    email=f"{username1}@example.com",
                    role="user",
                )
                user2 = User(
                    username=username2,
                    email=f"{username2}@example.com",
                    role="user",
                )
                setup_session.add_all([user1, user2])
                await setup_session.flush()

                resume = await resume_repository.create(
                    user_id=user1.user_id,
                    title="Persisted Agent Resume",
                )
                resume_version = await version_repository.create_for_user(
                    resume_id=resume.resume_id,
                    user_id=user1.user_id,
                    version_no=1,
                    raw_text="Python FastAPI resume",
                )
                job = await job_repository.create(
                    user_id=user1.user_id,
                    raw_description="Python FastAPI backend role",
                    title="Backend Engineer",
                )
                task = await create_persisted_task(
                    setup_session,
                    user_id=user1.user_id,
                    job_id=job.job_id,
                    resume_version_id=resume_version.resume_version_id,
                    conversation_id=None,
                )

                user1_id = user1.user_id
                user2_id = user2.user_id
                job_id = job.job_id
                resume_version_id = resume_version.resume_version_id
                task_id = task.task_id
                current_task_id = task_id

                if task.status != "pending":
                    raise AssertionError("任务初始状态不是 pending")
                print("task_create_pending_ok")

        result = await run_persisted_task(
            async_session_factory,
            user_id=user1_id,
            task_id=task_id,
        )
        if result.status != "completed":
            raise AssertionError("持久化 Agent 未完成")
        print("persisted_agent_completed_ok")

        async with async_session_factory() as session:
            task_repository = AnalysisTaskRepository(session)
            report_repository = ReportRepository(session)

            task = await task_repository.get_for_user(
                task_id=task_id,
                user_id=user1_id,
            )
            if (
                task is None
                or task.status != "completed"
                or task.attempt != 1
                or task.finished_at is None
            ):
                raise AssertionError("任务状态或尝试次数不正确")
            print("task_attempt_ok")

            current_report = await report_repository.get_current_for_user(
                task_id=task_id,
                user_id=user1_id,
            )
            if (
                current_report is None
                or current_report.report_id != result.report_id
                or current_report.version_no != result.report_version
            ):
                raise AssertionError("当前报告不正确")
            print("current_report_ok")

        try:
            await run_persisted_task(
                async_session_factory,
                user_id=user2_id,
                task_id=task_id,
            )
        except LookupError:
            print("cross_user_run_rejected")
        else:
            raise AssertionError("跨用户任务执行未被拒绝")

        try:
            await run_persisted_task(
                async_session_factory,
                user_id=user1_id,
                task_id=task_id,
            )
        except TaskStateConflictError:
            print("completed_task_rerun_rejected")
        else:
            raise AssertionError("completed 任务被重复执行")

        async with async_session_factory() as setup_session:
            async with setup_session.begin():
                failed_task = await create_persisted_task(
                    setup_session,
                    user_id=user1_id,
                    job_id=job_id,
                    resume_version_id=resume_version_id,
                    conversation_id=None,
                )
                failed_task_id = failed_task.task_id

        async def failing_chat_with_tools(*, messages, tools):
            raise LLMServiceError(
                message="模拟模型调用失败",
                status_code=504,
            )

        react_agent.chat_with_tools = failing_chat_with_tools

        try:
            await run_persisted_task(
                async_session_factory,
                user_id=user1_id,
                task_id=failed_task_id,
            )
        except LLMServiceError:
            pass
        else:
            raise AssertionError("模拟模型异常未传播")

        async with async_session_factory() as session:
            failed_task = await AnalysisTaskRepository(
                session
            ).get_for_user(
                task_id=failed_task_id,
                user_id=user1_id,
            )
            if (
                failed_task is None
                or failed_task.status != "interrupted"
                or failed_task.error_code != "llm_service_error"
                or failed_task.finished_at is None
            ):
                raise AssertionError("中断状态未正确持久化")
            print("interrupted_state_persisted")
        await cleanup_test_data([username1, username2])

        async with async_session_factory() as session:
            remaining_user = await session.scalar(
                select(User).where(User.username == username1)
            )
            if remaining_user is not None:
                raise AssertionError("测试用户未清理")
        print("rollback_cleanup_ok")
    finally:
        react_agent.chat_with_tools = original_chat_with_tools
        try:
            await cleanup_test_data([username1, username2])
        finally:
            await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_persisted_agent())
