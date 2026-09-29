# 验证 interrupted 任务的尝试递增、报告版本和恢复执行。

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

async def check_task_recovery() -> None:
    suffix = uuid4().hex
    username = f"recovery_user_{suffix}"
    llm_failure_count = 0
    success_count = 0

    async def llm_failure_chat(*, messages, tools):
        nonlocal llm_failure_count
        llm_failure_count += 1

        if llm_failure_count == 1:
            return LLMWithToolsResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="recovery-profile",
                        name="get_resume_profile",
                        arguments="{}",
                    )
                ],
                usage=usage(10, 2),
                latency_ms=10,
            )

        raise LLMServiceError(
            message="模拟 LLM 服务失败",
            status_code=503,
        )

    async def success_chat(*, messages, tools):
        nonlocal success_count
        success_count += 1

        if success_count == 1:
            return LLMWithToolsResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="recovery-success-profile",
                        name="get_resume_profile",
                        arguments="{}",
                    )
                ],
                usage=usage(10, 2),
                latency_ms=10,
            )

        if success_count == 2:
            return LLMWithToolsResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="recovery-success-report",
                        name="save_match_report",
                        arguments=json.dumps(
                            {
                                "summary": "Recovered report",
                                "result_json": {"status": "completed"},
                            }
                        ),
                    )
                ],
                usage=usage(12, 3),
                latency_ms=11,
            )

        return LLMWithToolsResult(
            content="Recovered analysis completed.",
            tool_calls=[],
            usage=usage(20, 5),
            latency_ms=12,
        )

    original_chat_with_tools = react_agent.chat_with_tools

    try:
        async with async_session_factory() as setup_session:
            async with setup_session.begin():
                user = User(
                    username=username,
                    email=f"{username}@example.com",
                    role="user",
                )
                setup_session.add(user)
                await setup_session.flush()

                resume = await ResumeRepository(setup_session).create(
                    user_id=user.user_id,
                    title="Recovery Resume",
                )
                resume_version = await ResumeVersionRepository(
                    setup_session
                ).create_for_user(
                    resume_id=resume.resume_id,
                    user_id=user.user_id,
                    version_no=1,
                    raw_text="Python FastAPI resume",
                )
                job = await JobRepository(setup_session).create(
                    user_id=user.user_id,
                    raw_description="Python FastAPI role",
                    title="Backend",
                )
                task = await create_persisted_task(
                    setup_session,
                    user_id=user.user_id,
                    job_id=job.job_id,
                    resume_version_id=resume_version.resume_version_id,
                    conversation_id=None,
                )
                user_id = user.user_id
                job_id = job.job_id
                resume_version_id = resume_version.resume_version_id
                task_id = task.task_id

        react_agent.chat_with_tools = llm_failure_chat

        try:
            await run_persisted_task(
                async_session_factory,
                user_id=user_id,
                task_id=task_id,
            )
        except LLMServiceError:
            pass
        else:
            raise AssertionError("LLMServiceError 未传播")

        async with async_session_factory() as session:
            task = await AnalysisTaskRepository(session).get_for_user(
                task_id=task_id,
                user_id=user_id,
            )
            interrupted_report = await ReportRepository(
                session
            ).get_current_for_user(
                task_id=task_id,
                user_id=user_id,
            )

        if (
            task is None
            or task.status != "interrupted"
            or task.error_code != "llm_service_error"
            or task.attempt != 1
        ):
            raise AssertionError("LLM 失败未标记 interrupted")
        if interrupted_report is None or interrupted_report.version_no != 1:
            raise AssertionError("中断报告版本不正确")
        print("llm_failure_marked_interrupted")

        react_agent.chat_with_tools = success_chat

        result = await run_persisted_task(
            async_session_factory,
            user_id=user_id,
            task_id=task_id,
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

        if task is None or task.status != "completed" or task.attempt != 2:
            raise AssertionError("恢复后 attempt 未递增")
        print("retry_attempt_incremented")

        if (
            report is None
            or report.version_no != 2
            or report.report_id != result.report_id
        ):
            raise AssertionError("恢复后报告版本未递增")
        print("retry_report_version_incremented")
        async with async_session_factory() as setup_session:
            async with setup_session.begin():
                max_steps_task = await create_persisted_task(
                    setup_session,
                    user_id=user_id,
                    job_id=job_id,
                    resume_version_id=resume_version_id,
                    conversation_id=None,
                )
                max_steps_task_id = max_steps_task.task_id

        max_steps_count = 0

        async def max_steps_chat(*, messages, tools):
            nonlocal max_steps_count
            max_steps_count += 1
            return LLMWithToolsResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id=f"max-step-{max_steps_count}",
                        name="get_resume_profile",
                        arguments="{}",
                    )
                ],
                usage=usage(5, 1),
                latency_ms=5,
            )

        react_agent.chat_with_tools = max_steps_chat

        max_steps_result = await run_persisted_task(
            async_session_factory,
            user_id=user_id,
            task_id=max_steps_task_id,
        )

        async with async_session_factory() as session:
            task = await AnalysisTaskRepository(session).get_for_user(
                task_id=max_steps_task_id,
                user_id=user_id,
            )
            report = await ReportRepository(session).get_current_for_user(
                task_id=max_steps_task_id,
                user_id=user_id,
            )

        if (
            max_steps_result.status != "interrupted"
            or task is None
            or task.status != "interrupted"
            or task.error_code != "max_steps_reached"
            or task.attempt != 1
            or report is None
            or report.version_no != 1
        ):
            raise AssertionError("max_steps 中断状态不正确")
        print("max_steps_marked_interrupted")

        success_count = 0
        react_agent.chat_with_tools = success_chat

        retry_result = await run_persisted_task(
            async_session_factory,
            user_id=user_id,
            task_id=max_steps_task_id,
        )

        async with async_session_factory() as session:
            task = await AnalysisTaskRepository(session).get_for_user(
                task_id=max_steps_task_id,
                user_id=user_id,
            )
            report = await ReportRepository(session).get_current_for_user(
                task_id=max_steps_task_id,
                user_id=user_id,
            )

        if (
            retry_result.status != "completed"
            or task is None
            or task.status != "completed"
            or task.attempt != 2
            or report is None
            or report.version_no != 2
        ):
            raise AssertionError("max_steps 恢复失败")
        print("max_steps_retry_completed")
    finally:
        react_agent.chat_with_tools = original_chat_with_tools
        try:
            await cleanup_test_data([username])
        finally:
            await dispose_engine()
        print("recovery_cleanup_ok")


if __name__ == "__main__":
    asyncio.run(check_task_recovery())