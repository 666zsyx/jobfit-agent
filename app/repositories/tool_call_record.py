# 提供按用户隔离的工具调用审计记录数据访问。

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalysisTask, ToolCallRecord
from app.repositories.analysis_task import AnalysisTaskRepository


class ToolCallRecordRepository:
    """工具调用审计记录 Repository。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_user(
        self,
        tool_call_record_id: int,
        user_id: int,
    ) -> ToolCallRecord | None:
        statement = (
            select(ToolCallRecord)
            .join(
                AnalysisTask,
                ToolCallRecord.task_id == AnalysisTask.task_id,
            )
            .where(
                ToolCallRecord.tool_call_record_id
                == tool_call_record_id,
                AnalysisTask.user_id == user_id,
                AnalysisTask.deleted_at.is_(None),
            )
        )
        return await self.session.scalar(statement)

    async def list_for_user(
        self,
        task_id: int,
        user_id: int,
    ) -> list[ToolCallRecord]:
        statement = (
            select(ToolCallRecord)
            .join(
                AnalysisTask,
                ToolCallRecord.task_id == AnalysisTask.task_id,
            )
            .where(
                ToolCallRecord.task_id == task_id,
                AnalysisTask.user_id == user_id,
                AnalysisTask.deleted_at.is_(None),
            )
            .order_by(
                ToolCallRecord.step_no,
                ToolCallRecord.tool_call_record_id,
            )
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def create_started_for_user(
        self,
        task_id: int,
        user_id: int,
        step_no: int,
        tool_call_id: str,
        tool_name: str,
        argument_keys: list[str] | None = None,
    ) -> ToolCallRecord:
        task_repository = AnalysisTaskRepository(self.session)
        task = await task_repository.get_for_user(
            task_id=task_id,
            user_id=user_id,
            for_update=True,
        )
        if task is None:
            raise LookupError("任务不存在或无权访问")

        record = ToolCallRecord(
            task_id=task_id,
            step_no=step_no,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            status="started",
            duration_ms=None,
            argument_keys=(
                {"keys": argument_keys}
                if argument_keys is not None
                else None
            ),
            error_code=None,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def finish_for_user(
        self,
        tool_call_record_id: int,
        user_id: int,
        status: str,
        duration_ms: int,
        error_code: str | None = None,
    ) -> ToolCallRecord:
        statement = (
            select(ToolCallRecord)
            .join(
                AnalysisTask,
                ToolCallRecord.task_id == AnalysisTask.task_id,
            )
            .where(
                ToolCallRecord.tool_call_record_id
                == tool_call_record_id,
                AnalysisTask.user_id == user_id,
                AnalysisTask.deleted_at.is_(None),
            )
            .with_for_update()
        )
        record = await self.session.scalar(statement)
        if record is None:
            raise LookupError("工具调用记录不存在或无权访问")

        record.status = status
        record.duration_ms = duration_ms
        record.error_code = error_code
        await self.session.flush()
        return record
