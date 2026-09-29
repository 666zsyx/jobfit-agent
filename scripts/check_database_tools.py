# 验证数据库工具的用户隔离、报告持久化和事务回滚。

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import AnalysisTask, Report, User
from app.db.session import async_session_factory, dispose_engine
from app.repositories import (
    JobRepository,
    ReportRepository,
    ResumeRepository,
    ResumeVersionRepository,
)
from app.schemas.auth import CurrentUser
from app.services.analysis_tasks import create_analysis_task
from app.tools import ToolContext
from app.tools.executor import execute_tool
from app.tools.jobfit import build_jobfit_tool_registry


async def check_database_tools() -> None:
    suffix = uuid4().hex
    username1 = f"db_tool_user1_{suffix}"
    username2 = f"db_tool_user2_{suffix}"
    task_id: int | None = None

    try:
        async with async_session_factory() as session:
            try:
                resume_repository = ResumeRepository(session)
                version_repository = ResumeVersionRepository(session)
                job_repository = JobRepository(session)
                report_repository = ReportRepository(session)

                user1 = User(
                    username=username1,
                    email=f"{username1}@example.com",
                )
                user2 = User(
                    username=username2,
                    email=f"{username2}@example.com",
                )
                session.add_all([user1, user2])
                await session.flush()

                resume = await resume_repository.create(
                    user_id=user1.user_id,
                    title="Database Tool Resume",
                )
                resume_version = await version_repository.create_for_user(
                    resume_id=resume.resume_id,
                    user_id=user1.user_id,
                    version_no=1,
                    raw_text="Python FastAPI resume",
                    extracted_sections={"sections": []},
                )
                job = await job_repository.create(
                    user_id=user1.user_id,
                    raw_description="Python FastAPI backend role",
                    title="Backend Engineer",
                )
                task = await create_analysis_task(
                    session,
                    user_id=user1.user_id,
                    job_id=job.job_id,
                    resume_version_id=resume_version.resume_version_id,
                )
                task_id = task.task_id

                registry = build_jobfit_tool_registry()
                context1 = ToolContext(
                    current_user=CurrentUser(
                        id=user1.user_id,
                        username=user1.username,
                        role=user1.role,
                    ),
                    session=session,
                    task_id=task.task_id,
                    step_no=1,
                )

                profile_result = await execute_tool(
                    registry=registry,
                    tool_name="get_resume_profile",
                    arguments={},
                    context=context1,
                )
                profile = profile_result["result"]

                if (
                    not profile_result["ok"]
                    or not profile["found"]
                    or profile["resume_id"] != resume.resume_id
                    or profile["resume_version_id"]
                    != resume_version.resume_version_id
                    or profile["raw_text"] != "Python FastAPI resume"
                ):
                    raise AssertionError("get_resume_profile 返回不正确")
                print("get_resume_profile_ok")

                report1_result = await execute_tool(
                    registry=registry,
                    tool_name="save_match_report",
                    arguments={
                        "summary": "Report version 1",
                        "result_json": {"version": 1},
                    },
                    context=context1,
                )
                report1 = report1_result["result"]
                if (
                    not report1_result["ok"]
                    or not report1["saved"]
                    or report1["version_no"] != 1
                    or not report1["is_current"]
                ):
                    raise AssertionError("报告版本 1 保存失败")
                print("save_report_version_1_ok")

                report2_result = await execute_tool(
                    registry=registry,
                    tool_name="save_match_report",
                    arguments={
                        "summary": "Report version 2",
                        "result_json": {"version": 2},
                    },
                    context=context1,
                )
                report2 = report2_result["result"]
                if (
                    not report2_result["ok"]
                    or not report2["saved"]
                    or report2["version_no"] != 2
                    or not report2["is_current"]
                ):
                    raise AssertionError("报告版本 2 保存失败")
                print("save_report_version_2_ok")

                current_report = (
                    await report_repository.get_current_for_user(
                        task_id=task.task_id,
                        user_id=user1.user_id,
                    )
                )
                if (
                    current_report is None
                    or current_report.report_id != report2["report_id"]
                    or current_report.version_no != 2
                ):
                    raise AssertionError("当前报告版本不正确")
                print("current_report_ok")

                context2 = ToolContext(
                    current_user=CurrentUser(
                        id=user2.user_id,
                        username=user2.username,
                        role=user2.role,
                    ),
                    session=session,
                    task_id=task.task_id,
                    step_no=1,
                )

                other_profile_result = await execute_tool(
                    registry=registry,
                    tool_name="get_resume_profile",
                    arguments={},
                    context=context2,
                )
                if other_profile_result != {
                    "ok": True,
                    "result": {"found": False},
                }:
                    raise AssertionError("跨用户简历读取未被隐藏")
                print("cross_user_profile_hidden")

                other_report_result = await execute_tool(
                    registry=registry,
                    tool_name="save_match_report",
                    arguments={
                        "summary": "Cross-user report",
                        "result_json": {"version": 3},
                    },
                    context=context2,
                )
                other_report = other_report_result["result"]
                if (
                    not other_report_result["ok"]
                    or other_report["saved"]
                    or other_report["error"]
                    != "任务不存在或无权访问"
                ):
                    raise AssertionError("跨用户报告保存未被拒绝")
                print("cross_user_report_rejected")

                if not session.in_transaction():
                    raise AssertionError("工具不应提交事务")

                await session.rollback()

                cleaned_user = await session.scalar(
                    select(User).where(User.username == username1)
                )
                if cleaned_user is not None:
                    raise AssertionError("测试用户未随事务回滚")

                task_count = await session.scalar(
                    select(func.count())
                    .select_from(AnalysisTask)
                    .where(AnalysisTask.task_id == task_id)
                )
                report_count = await session.scalar(
                    select(func.count())
                    .select_from(Report)
                    .where(Report.task_id == task_id)
                )
                if task_count or report_count:
                    raise AssertionError("测试任务或报告未完全回滚")
                print("rollback_cleanup_ok")
            except Exception:
                await session.rollback()
                raise
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_database_tools())
