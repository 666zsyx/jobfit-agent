# 验证 ReAct 执行期间不持有数据库事务和任务行锁。

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, func, select

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
async def check_task_transaction_boundaries() -> None:
    suffix = uuid4().hex
    username = f"boundary_user_{suffix}"
    call_count = 0
    active_task_id: int | None = None
    running_seen = False
    no_lock_during_model = False
    deferred_not_persisted = False

    async def fake_chat_with_tools(*, messages, tools):
        nonlocal call_count
        nonlocal running_seen
        nonlocal no_lock_during_model
        nonlocal deferred_not_persisted

        call_count += 1

        if call_count == 1:
            async with async_session_factory() as check_session:
                async with check_session.begin():
                    locked_task = await check_session.scalar(
                        select(AnalysisTask)
                        .where(AnalysisTask.task_id == active_task_id)
                        .with_for_update(nowait=True)
                    )
                    if locked_task is None or locked_task.status != "running":
                        raise AssertionError("阶段 1 未提交 running 状态")
                    running_seen = True
                    no_lock_during_model = True

            return LLMWithToolsResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="boundary-profile",
                        name="get_resume_profile",
                        arguments="{}",
                    )
                ],
                usage=usage(10, 2),
                latency_ms=10,
            )

        if call_count == 2:
            async with async_session_factory() as check_session:
                report_count = await check_session.scalar(
                    select(func.count())
                    .select_from(Report)
                    .where(Report.task_id == active_task_id)
                )
                if report_count != 0:
                    raise AssertionError("模型调用期间报告已提前写入")

            return LLMWithToolsResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="boundary-report",
                        name="save_match_report",
                        arguments=json.dumps(
                            {
                                "summary": "Boundary report",
                                "result_json": {"matches": []},
                            },
                            ensure_ascii=False,
                        ),
                    )
                ],
                usage=usage(12, 3),
                latency_ms=11,
            )

        async with async_session_factory() as check_session:
            report_count = await check_session.scalar(
                select(func.count())
                .select_from(Report)
                .where(Report.task_id == active_task_id)
            )
            if report_count != 0:
                raise AssertionError("延迟报告在模型返回前已写入")
            deferred_not_persisted = True

        return LLMWithToolsResult(
            content="Boundary analysis completed.",
            tool_calls=[],
            usage=usage(20, 5),
            latency_ms=12,
        )

    original_chat_with_tools = react_agent.chat_with_tools
    react_agent.chat_with_tools = fake_chat_with_tools

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
                    title="Boundary Resume",
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
                active_task_id = task.task_id

        result = await run_persisted_task(
            async_session_factory,
            user_id=user_id,
            task_id=active_task_id,
        )

        if not running_seen:
            raise AssertionError("未观察 running 提交")
        print("running_committed_before_model")

        if not no_lock_during_model:
            raise AssertionError("模型期间仍持有任务锁")
        print("no_task_lock_during_model")

        if not deferred_not_persisted:
            raise AssertionError("延迟报告检查失败")
        print("deferred_report_not_persisted")

        async with async_session_factory() as session:
            task = await AnalysisTaskRepository(session).get_for_user(
                task_id=active_task_id,
                user_id=user_id,
            )
            report = await ReportRepository(session).get_current_for_user(
                task_id=active_task_id,
                user_id=user_id,
            )
            if (
                task is None
                or task.status != "completed"
                or report is None
                or report.report_id != result.report_id
                or report.version_no != result.report_version
            ):
                raise AssertionError("最终任务或报告状态不正确")
        print("final_report_committed")
        print("completed_state_committed")

        async with async_session_factory() as setup_session:
            async with setup_session.begin():
                completed_task = await AnalysisTaskRepository(
                    setup_session
                ).get_for_user(
                    task_id=active_task_id,
                    user_id=user_id,
                )
                cancelled_task = await create_persisted_task(
                    setup_session,
                    user_id=user_id,
                    job_id=completed_task.job_id,
                    resume_version_id=completed_task.resume_version_id,
                    conversation_id=None,
                )
                cancelled_task_id = cancelled_task.task_id

        async def cancelling_chat_with_tools(*, messages, tools):
            async with async_session_factory() as cancel_session:
                async with cancel_session.begin():
                    task_to_cancel = await cancel_session.scalar(
                        select(AnalysisTask)
                        .where(AnalysisTask.task_id == cancelled_task_id)
                        .with_for_update()
                    )
                    task_to_cancel.status = "cancelled"
                    task_to_cancel.finished_at = func.now()
                    task_to_cancel.updated_at = func.now()

            return LLMWithToolsResult(
                content="Cancelled analysis.",
                tool_calls=[],
                usage=usage(10, 2),
                latency_ms=10,
            )

        react_agent.chat_with_tools = cancelling_chat_with_tools

        try:
            await run_persisted_task(
                async_session_factory,
                user_id=user_id,
                task_id=cancelled_task_id,
            )
        except TaskStateConflictError:
            pass
        else:
            raise AssertionError("取消后的任务状态冲突未传播")

        async with async_session_factory() as session:
            cancelled_task = await AnalysisTaskRepository(
                session
            ).get_for_user(
                task_id=cancelled_task_id,
                user_id=user_id,
            )
            cancelled_report_count = await session.scalar(
                select(func.count())
                .select_from(Report)
                .where(Report.task_id == cancelled_task_id)
            )
            if (
                cancelled_task is None
                or cancelled_task.status != "cancelled"
                or cancelled_task.error_code is not None
                or cancelled_report_count != 0
            ):
                raise AssertionError("cancelled 状态被失败处理覆盖")
        print("cancelled_state_not_overwritten")

        async with async_session_factory() as setup_session:
            async with setup_session.begin():
                completed_task = await AnalysisTaskRepository(
                    setup_session
                ).get_for_user(
                    task_id=active_task_id,
                    user_id=user_id,
                )
                failed_task = await create_persisted_task(
                    setup_session,
                    user_id=user_id,
                    job_id=completed_task.job_id,
                    resume_version_id=completed_task.resume_version_id,
                    conversation_id=None,
                )
                failed_task_id = failed_task.task_id

        async def failing_chat_with_tools(*, messages, tools):
            raise LLMServiceError(
                message="模拟模型失败",
                status_code=504,
            )

        react_agent.chat_with_tools = failing_chat_with_tools

        try:
            await run_persisted_task(
                async_session_factory,
                user_id=user_id,
                task_id=failed_task_id,
            )
        except LLMServiceError:
            pass
        else:
            raise AssertionError("模型异常未传播")

        async with async_session_factory() as session:
            failed_task = await AnalysisTaskRepository(
                session
            ).get_for_user(
                task_id=failed_task_id,
                user_id=user_id,
            )
            if (
                failed_task is None
                or failed_task.status != "interrupted"
                or failed_task.error_code != "llm_service_error"
                or failed_task.finished_at is None
            ):
                raise AssertionError("中断状态未提交")
        print("interrupted_state_committed")
        print("transaction_boundaries_ok")
    finally:
        react_agent.chat_with_tools = original_chat_with_tools
        try:
            await cleanup_test_data([username])
        finally:
            await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_task_transaction_boundaries())
