# 验证工具调用审计和报告持久化的用户隔离与事务边界。

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import AnalysisTask, Report, ToolCallRecord, User
from app.db.session import async_session_factory, dispose_engine
from app.repositories import (
    ConversationRepository,
    JobRepository,
    ReportRepository,
    ResumeRepository,
    ResumeVersionRepository,
    ToolCallRecordRepository,
    UserRepository,
)
from app.services.analysis_results import (
    finish_tool_call,
    save_analysis_report,
    start_tool_call,
)
from app.services.analysis_tasks import create_analysis_task


async def check_result_persistence() -> None:
    suffix = uuid4().hex
    username1 = f"result_user1_{suffix}"
    username2 = f"result_user2_{suffix}"

    try:
        async with async_session_factory() as session:
            try:
                user_repository = UserRepository(session)
                resume_repository = ResumeRepository(session)
                version_repository = ResumeVersionRepository(session)
                job_repository = JobRepository(session)
                conversation_repository = ConversationRepository(session)
                report_repository = ReportRepository(session)
                tool_repository = ToolCallRecordRepository(session)

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

                resume1 = await resume_repository.create(
                    user_id=user1.user_id,
                    title="Result User 1 Resume",
                )
                version1 = await version_repository.create_for_user(
                    resume_id=resume1.resume_id,
                    user_id=user1.user_id,
                    version_no=1,
                    raw_text="Result user 1 resume",
                )
                job1 = await job_repository.create(
                    user_id=user1.user_id,
                    raw_description="Result user 1 job",
                    title="Backend",
                )
                conversation1 = await conversation_repository.create(
                    user_id=user1.user_id,
                    title="Result user 1 conversation",
                )
                task1 = await create_analysis_task(
                    session,
                    user_id=user1.user_id,
                    job_id=job1.job_id,
                    resume_version_id=version1.resume_version_id,
                    conversation_id=conversation1.conversation_id,
                )

                call1 = await start_tool_call(
                    session,
                    user_id=user1.user_id,
                    task_id=task1.task_id,
                    step_no=1,
                    tool_call_id="call-1",
                    tool_name="extract_job_requirements",
                    argument_keys=["job_description"],
                )
                call1 = await finish_tool_call(
                    session,
                    user_id=user1.user_id,
                    tool_call_record_id=call1.tool_call_record_id,
                    status="success",
                    duration_ms=120,
                )

                call2 = await start_tool_call(
                    session,
                    user_id=user1.user_id,
                    task_id=task1.task_id,
                    step_no=2,
                    tool_call_id="call-2",
                    tool_name="search_resume_evidence",
                    argument_keys=["requirements", "sections"],
                )
                call2 = await finish_tool_call(
                    session,
                    user_id=user1.user_id,
                    tool_call_record_id=call2.tool_call_record_id,
                    status="timeout",
                    duration_ms=5000,
                    error_code="tool_timeout",
                )
                if (
                    call1.status != "success"
                    or call1.duration_ms != 120
                    or call2.status != "timeout"
                    or call2.error_code != "tool_timeout"
                ):
                    raise AssertionError("工具调用终态不正确")
                print("tool_call_start_finish_ok")

                report1 = await save_analysis_report(
                    session,
                    user_id=user1.user_id,
                    task_id=task1.task_id,
                    summary="Report version 1",
                    result_json={"version": 1},
                    current_step=1,
                )
                if report1.version_no != 1 or not report1.is_current:
                    raise AssertionError("报告版本 1 不正确")
                print("report_version_1_ok")

                report2 = await save_analysis_report(
                    session,
                    user_id=user1.user_id,
                    task_id=task1.task_id,
                    summary="Report version 2",
                    result_json={"version": 2},
                    current_step=2,
                )
                if report2.version_no != 2 or not report2.is_current:
                    raise AssertionError("报告版本 2 不正确")
                print("report_version_2_ok")

                await session.refresh(report1)
                current_report = (
                    await report_repository.get_current_for_user(
                        task_id=task1.task_id,
                        user_id=user1.user_id,
                    )
                )
                if report1.is_current:
                    raise AssertionError("旧报告仍然是当前报告")
                if current_report is None or current_report.report_id != report2.report_id:
                    raise AssertionError("当前报告切换失败")
                print("current_report_switch_ok")

                await session.refresh(task1)
                if task1.status != "completed" or task1.current_step != 2:
                    raise AssertionError("任务没有正确完成")
                if task1.finished_at is None:
                    raise AssertionError("任务完成时间未写入")
                print("task_completed_ok")

                tool_records = await tool_repository.list_for_user(
                    task_id=task1.task_id,
                    user_id=user1.user_id,
                )
                if len(tool_records) != 2:
                    raise AssertionError("工具调用记录数量不正确")
                print("tool_record_isolation_ok")
                other_tool_records = await tool_repository.list_for_user(
                    task_id=task1.task_id,
                    user_id=user2.user_id,
                )
                if other_tool_records:
                    raise AssertionError("跨用户工具记录隔离失败")
                print("tool_record_read_isolation_ok")

                try:
                    await finish_tool_call(
                        session,
                        user_id=user1.user_id,
                        tool_call_record_id=call1.tool_call_record_id,
                        status="started",
                        duration_ms=1,
                    )
                except ValueError:
                    print("invalid_finish_status_rejected")
                else:
                    raise AssertionError("非终态工具状态未被拒绝")

                try:
                    await finish_tool_call(
                        session,
                        user_id=user1.user_id,
                        tool_call_record_id=call1.tool_call_record_id,
                        status="success",
                        duration_ms=-1,
                    )
                except ValueError:
                    print("negative_duration_rejected")
                else:
                    raise AssertionError("负数工具耗时未被拒绝")

                other_reports = await report_repository.list_for_user(
                    task_id=task1.task_id,
                    user_id=user2.user_id,
                )
                if other_reports:
                    raise AssertionError("跨用户报告隔离失败")
                print("report_isolation_ok")

                try:
                    await save_analysis_report(
                        session,
                        user_id=user2.user_id,
                        task_id=task1.task_id,
                        summary="Cross-user report",
                        result_json={"version": 3},
                        current_step=3,
                    )
                except LookupError:
                    print("cross_user_report_rejected")
                else:
                    raise AssertionError("跨用户保存报告未被拒绝")

                try:
                    await finish_tool_call(
                        session,
                        user_id=user2.user_id,
                        tool_call_record_id=call1.tool_call_record_id,
                        status="success",
                        duration_ms=999,
                    )
                except LookupError:
                    print("cross_user_tool_update_rejected")
                else:
                    raise AssertionError("跨用户更新工具记录未被拒绝")

                task1_id = task1.task_id
                await session.rollback()

                if await user_repository.get_by_username(username1) is not None:
                    raise AssertionError("测试用户未回滚")

                task_count = await session.scalar(
                    select(func.count())
                    .select_from(AnalysisTask)
                    .where(AnalysisTask.task_id == task1_id)
                )
                report_count = await session.scalar(
                    select(func.count())
                    .select_from(Report)
                    .where(Report.task_id == task1_id)
                )
                tool_count = await session.scalar(
                    select(func.count())
                    .select_from(ToolCallRecord)
                    .where(ToolCallRecord.task_id == task1_id)
                )
                if task_count or report_count or tool_count:
                    raise AssertionError("持久化测试数据未完全回滚")
                print("rollback_cleanup_ok")
            except Exception:
                await session.rollback()
                raise
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_result_persistence())

