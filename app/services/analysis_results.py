# 保存分析结果和工具调用审计记录。

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalysisTask, Report, ToolCallRecord
from app.repositories import (
    AnalysisTaskRepository,
    ReportRepository,
    ToolCallRecordRepository,
)
from app.schemas.tool_audit import ToolAuditEvent

FINAL_TOOL_CALL_STATUSES = {
    "success",
    "validation_error",
    "timeout",
    "error",
    "unknown_tool",
}


COMPLETABLE_TASK_STATUSES = {
    "completed",
    "interrupted",
    "failed",
    "cancelled",
}


async def save_analysis_report(
    session: AsyncSession,
    *,
    user_id: int,
    task_id: int,
    summary: str,
    result_json: dict,
    current_step: int,
) -> Report:
    """保存任务报告，并将任务更新为 completed。"""

    if current_step < 0:
        raise ValueError("current_step 不能小于 0")

    task_repository = AnalysisTaskRepository(session)
    report_repository = ReportRepository(session)

    task = await task_repository.get_for_user(
        task_id=task_id,
        user_id=user_id,
        for_update=True,
    )
    if task is None:
        raise LookupError("任务不存在或无权访问")

    if current_step > task.max_steps:
        raise ValueError("current_step 不能超过 max_steps")

    report = await report_repository.create_for_user(
        task_id=task_id,
        user_id=user_id,
        summary=summary,
        result_json=result_json,
        make_current=True,
    )

    task.status = "completed"
    task.current_step = current_step
    task.finished_at = func.now()
    task.updated_at = func.now()
    await session.flush()
    return report


async def start_tool_call(
    session: AsyncSession,
    *,
    user_id: int,
    task_id: int,
    step_no: int,
    tool_call_id: str,
    tool_name: str,
    argument_keys: list[str] | None = None,
) -> ToolCallRecord:
    """创建 started 状态的工具调用记录。"""

    repository = ToolCallRecordRepository(session)
    return await repository.create_started_for_user(
        task_id=task_id,
        user_id=user_id,
        step_no=step_no,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        argument_keys=argument_keys,
    )


async def finish_tool_call(
    session: AsyncSession,
    *,
    user_id: int,
    tool_call_record_id: int,
    status: str,
    duration_ms: int,
    error_code: str | None = None,
) -> ToolCallRecord:
    """更新工具调用记录的安全终态信息。"""

    if status not in FINAL_TOOL_CALL_STATUSES:
        raise ValueError("工具调用终态不合法")

    if duration_ms < 0:
        raise ValueError("duration_ms 不能小于 0")

    repository = ToolCallRecordRepository(session)
    return await repository.finish_for_user(
        tool_call_record_id=tool_call_record_id,
        user_id=user_id,
        status=status,
        duration_ms=duration_ms,
        error_code=error_code,
    )


async def recover_stale_running_tasks(
    session: AsyncSession,
) -> int:
    """把上次进程遗留的 running 任务转为可恢复中断。"""

    statement = (
        update(AnalysisTask)
        .where(AnalysisTask.status == "running")
        .values(
            status="interrupted",
            error_code="server_restarted",
            error_message_safe="server_restarted",
            finished_at=func.now(),
            updated_at=func.now(),
        )
        .returning(AnalysisTask.task_id)
    )
    result = await session.scalars(statement)
    return len(result.all())


async def complete_analysis_task(
    session: AsyncSession,
    *,
    user_id: int,
    task_id: int,
    status: str,
    current_step: int,
    error_code: str | None = None,
    current_node: str | None = None,
    metrics_json: dict | None = None,
    last_request_id: str | None = None,
) -> AnalysisTask:
    """更新任务终态，但不提交当前事务。"""

    if status not in COMPLETABLE_TASK_STATUSES:
        raise ValueError("任务终态不合法")

    if current_step < 0:
        raise ValueError("current_step 不能小于 0")

    repository = AnalysisTaskRepository(session)
    task = await repository.get_for_user(
        task_id=task_id,
        user_id=user_id,
        for_update=True,
    )
    if task is None:
        raise LookupError("任务不存在或无权访问")

    if current_step > task.max_steps:
        raise ValueError("current_step 不能超过 max_steps")

    task.status = status
    task.current_step = current_step
    if current_node is not None:
        task.current_node = current_node
    if metrics_json is not None:
        task.metrics_json = metrics_json
    if last_request_id is not None:
        task.last_request_id = last_request_id
    task.finished_at = func.now()
    task.updated_at = func.now()

    if status == "completed":
        task.error_code = None
        task.error_message_safe = None
    else:
        task.error_code = error_code
        task.error_message_safe = error_code

    await session.flush()
    return task


async def mark_analysis_task_failed(
    session: AsyncSession,
    *,
    user_id: int,
    task_id: int,
    error_code: str,
) -> AnalysisTask:
    """在独立事务中保存安全的任务失败状态。"""

    repository = AnalysisTaskRepository(session)
    task = await repository.get_for_user(
        task_id=task_id,
        user_id=user_id,
        for_update=True,
    )
    if task is None:
        raise LookupError("任务不存在或无权访问")

    if task.status != "running":
        return task

    task.status = "failed"
    task.error_code = error_code
    task.error_message_safe = error_code
    task.finished_at = func.now()
    task.updated_at = func.now()
    await session.flush()
    return task


async def mark_analysis_task_interrupted(
    session: AsyncSession,
    *,
    user_id: int,
    task_id: int,
    error_code: str,
) -> AnalysisTask:
    """只把运行中的任务标记为可恢复中断。"""

    repository = AnalysisTaskRepository(session)
    task = await repository.get_for_user(
        task_id=task_id,
        user_id=user_id,
        for_update=True,
    )
    if task is None:
        raise LookupError("任务不存在或无权访问")

    if task.status != "running":
        return task

    task.status = "interrupted"
    task.error_code = error_code
    task.error_message_safe = error_code
    task.finished_at = func.now()
    task.updated_at = func.now()
    await session.flush()
    return task


async def mark_analysis_task_waiting_confirmation(
    session: AsyncSession,
    *,
    user_id: int,
    task_id: int,
    current_step: int,
    current_node: str,
    metrics_json: dict | None = None,
    last_request_id: str | None = None,
) -> AnalysisTask:
    """把运行中的任务标记为等待人工确认。"""

    repository = AnalysisTaskRepository(session)
    task = await repository.get_for_user(
        task_id=task_id,
        user_id=user_id,
        for_update=True,
    )
    if task is None:
        raise LookupError("任务不存在或无权访问")

    if task.status != "running":
        return task

    task.status = "waiting_confirmation"
    task.current_step = current_step
    task.current_node = current_node
    if metrics_json is not None:
        task.metrics_json = metrics_json
    if last_request_id is not None:
        task.last_request_id = last_request_id
    task.error_code = None
    task.error_message_safe = None
    task.finished_at = None
    task.updated_at = func.now()
    await session.flush()
    return task


async def persist_tool_audit_events(
    session: AsyncSession,
    *,
    user_id: int,
    task_id: int,
    events: list[ToolAuditEvent],
) -> list[ToolCallRecord]:
    """把内存中的工具审计事件写入当前任务。"""

    if not events:
        return []

    repository = ToolCallRecordRepository(session)
    records: list[ToolCallRecord] = []

    for event in events:
        if event.status == "started":
            final_status = "error"
            error_code = "audit_incomplete"
            duration_ms = event.duration_ms or 0
        else:
            final_status = event.status
            error_code = event.error_code
            duration_ms = event.duration_ms or 0

        record = await repository.create_started_for_user(
            task_id=task_id,
            user_id=user_id,
            step_no=event.step_no,
            tool_call_id=event.tool_call_id,
            tool_name=event.tool_name,
            argument_keys=event.argument_keys,
        )
        record = await repository.finish_for_user(
            tool_call_record_id=record.tool_call_record_id,
            user_id=user_id,
            status=final_status,
            duration_ms=duration_ms,
            error_code=error_code,
        )
        records.append(record)

    return records
