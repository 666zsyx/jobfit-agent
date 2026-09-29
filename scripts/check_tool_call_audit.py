# 验证工具调用审计从 ReAct 执行到数据库持久化的完整链路。

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
    ResumeRepository,
    ResumeVersionRepository,
    ToolCallRecordRepository,
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

async def check_tool_call_audit() -> None:
    suffix = uuid4().hex
    username1 = f"audit_user1_{suffix}"
    username2 = f"audit_user2_{suffix}"
    success_call_count = 0

    async def success_chat_with_tools(*, messages, tools):
        nonlocal success_call_count
        success_call_count += 1

        if success_call_count == 1:
            tool_call = ToolCall(
                id="audit-profile",
                name="get_resume_profile",
                arguments="{}",
            )
        elif success_call_count == 2:
            tool_call = ToolCall(
                id="audit-unknown",
                name="unknown_tool",
                arguments="{}",
            )
        elif success_call_count == 3:
            tool_call = ToolCall(
                id="audit-invalid-report",
                name="save_match_report",
                arguments=json.dumps({"summary": "Missing result"}),
            )
        elif success_call_count == 4:
            tool_call = ToolCall(
                id="audit-report",
                name="save_match_report",
                arguments=json.dumps(
                    {
                        "summary": "Sensitive report summary",
                        "result_json": {
                            "secret_result": "must-not-be-stored"
                        },
                    },
                    ensure_ascii=False,
                ),
            )
        else:
            return LLMWithToolsResult(
                content="Audit analysis completed.",
                tool_calls=[],
                usage=usage(20, 5),
                latency_ms=12,
            )

        return LLMWithToolsResult(
            content=None,
            tool_calls=[tool_call],
            usage=usage(10, 2),
            latency_ms=10,
        )

    original_chat_with_tools = react_agent.chat_with_tools
    react_agent.chat_with_tools = success_chat_with_tools

    try:
        async with async_session_factory() as setup_session:
            async with setup_session.begin():
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

                resume = await ResumeRepository(setup_session).create(
                    user_id=user1.user_id,
                    title="Audit Resume",
                )
                resume_version = await ResumeVersionRepository(
                    setup_session
                ).create_for_user(
                    resume_id=resume.resume_id,
                    user_id=user1.user_id,
                    version_no=1,
                    raw_text="Python FastAPI resume",
                )
                job = await JobRepository(setup_session).create(
                    user_id=user1.user_id,
                    raw_description="Python FastAPI role",
                    title="Backend",
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
                task_id = task.task_id

        result = await run_persisted_task(
            async_session_factory,
            user_id=user1_id,
            task_id=task_id,
        )
        if result.status != "completed":
            raise AssertionError("审计验收任务未完成")

        async with async_session_factory() as session:
            records = await ToolCallRecordRepository(
                session
            ).list_for_user(
                task_id=task_id,
                user_id=user1_id,
            )

        if len(records) != 4:
            raise AssertionError("工具审计记录数量不正确")

        by_call_id = {record.tool_call_id: record for record in records}

        profile = by_call_id["audit-profile"]
        unknown = by_call_id["audit-unknown"]
        invalid_report = by_call_id["audit-invalid-report"]
        report = by_call_id["audit-report"]

        if profile.status != "success":
            raise AssertionError("get_resume_profile 审计状态不正确")
        if unknown.status != "unknown_tool":
            raise AssertionError("未知工具审计状态不正确")
        if invalid_report.status != "validation_error":
            raise AssertionError("参数错误审计状态不正确")
        if report.status != "success":
            raise AssertionError("save_match_report 审计状态不正确")

        if [profile.step_no, unknown.step_no, invalid_report.step_no, report.step_no] != [1, 2, 3, 4]:
            raise AssertionError("工具审计 step_no 不正确")

        if unknown.error_code != "unknown_tool":
            raise AssertionError("未知工具 error_code 不正确")
        if invalid_report.error_code != "validation_error":
            raise AssertionError("参数错误 error_code 不正确")
        if report.error_code is not None:
            raise AssertionError("成功工具不应有 error_code")

        if invalid_report.argument_keys != {"keys": ["summary"]}:
            raise AssertionError("参数错误 argument_keys 不正确")
        if report.argument_keys != {
            "keys": ["result_json", "summary"]
        }:
            raise AssertionError("成功工具 argument_keys 不正确")

        serialized_records = str(
            [record.argument_keys for record in records]
        )
        if "Sensitive report summary" in serialized_records:
            raise AssertionError("完整参数值被写入审计记录")
        if "must-not-be-stored" in serialized_records:
            raise AssertionError("工具结果正文被写入审计记录")

        print("tool_audit_success_recorded")
        print("tool_audit_unknown_recorded")
        print("tool_audit_validation_recorded")
        print("tool_audit_no_argument_values")
        async with async_session_factory() as session:
            other_records = await ToolCallRecordRepository(
                session
            ).list_for_user(
                task_id=task_id,
                user_id=user2_id,
            )
            if other_records:
                raise AssertionError("跨用户工具审计隔离失败")
        print("tool_audit_task_ownership_ok")

        async with async_session_factory() as setup_session:
            async with setup_session.begin():
                completed_task = await AnalysisTaskRepository(
                    setup_session
                ).get_for_user(
                    task_id=task_id,
                    user_id=user1_id,
                )
                failed_task = await create_persisted_task(
                    setup_session,
                    user_id=user1_id,
                    job_id=completed_task.job_id,
                    resume_version_id=completed_task.resume_version_id,
                    conversation_id=None,
                )
                failed_task_id = failed_task.task_id

        failure_call_count = 0

        async def failing_chat_with_tools(*, messages, tools):
            nonlocal failure_call_count
            failure_call_count += 1

            if failure_call_count == 1:
                return LLMWithToolsResult(
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id="audit-failure-profile",
                            name="get_resume_profile",
                            arguments="{}",
                        )
                    ],
                    usage=usage(10, 2),
                    latency_ms=10,
                )

            raise LLMServiceError(
                message="模拟模型失败",
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
            raise AssertionError("模型异常未传播")

        async with async_session_factory() as session:
            failed_task = await AnalysisTaskRepository(
                session
            ).get_for_user(
                task_id=failed_task_id,
                user_id=user1_id,
            )
            failure_records = await ToolCallRecordRepository(
                session
            ).list_for_user(
                task_id=failed_task_id,
                user_id=user1_id,
            )

        if (
            failed_task is None
            or failed_task.status != "interrupted"
            or failed_task.error_code != "llm_service_error"
        ):
            raise AssertionError("中断任务状态不正确")
        if (
            len(failure_records) != 1
            or failure_records[0].tool_call_id != "audit-failure-profile"
            or failure_records[0].status != "success"
        ):
            raise AssertionError("失败任务已完成审计未持久化")
        print("tool_audit_failure_persisted")
    finally:
        react_agent.chat_with_tools = original_chat_with_tools
        try:
            await cleanup_test_data([username1, username2])
        finally:
            await dispose_engine()
        print("tool_audit_cleanup_ok")


if __name__ == "__main__":
    asyncio.run(check_tool_call_audit())
