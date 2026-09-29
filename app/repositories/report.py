# 提供按用户隔离的分析报告数据访问。

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalysisTask, Report
from app.repositories.analysis_task import AnalysisTaskRepository


class ReportRepository:
    """分析报告 Repository。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_user(
        self,
        report_id: int,
        user_id: int,
    ) -> Report | None:
        statement = (
            select(Report)
            .join(
                AnalysisTask,
                Report.task_id == AnalysisTask.task_id,
            )
            .where(
                Report.report_id == report_id,
                Report.deleted_at.is_(None),
                AnalysisTask.user_id == user_id,
                AnalysisTask.deleted_at.is_(None),
            )
        )
        return await self.session.scalar(statement)

    async def get_current_for_user(
        self,
        task_id: int,
        user_id: int,
    ) -> Report | None:
        statement = (
            select(Report)
            .join(
                AnalysisTask,
                Report.task_id == AnalysisTask.task_id,
            )
            .where(
                Report.task_id == task_id,
                Report.is_current.is_(True),
                Report.deleted_at.is_(None),
                AnalysisTask.user_id == user_id,
                AnalysisTask.deleted_at.is_(None),
            )
        )
        return await self.session.scalar(statement)

    async def list_for_user(
        self,
        task_id: int,
        user_id: int,
    ) -> list[Report]:
        statement = (
            select(Report)
            .join(
                AnalysisTask,
                Report.task_id == AnalysisTask.task_id,
            )
            .where(
                Report.task_id == task_id,
                Report.deleted_at.is_(None),
                AnalysisTask.user_id == user_id,
                AnalysisTask.deleted_at.is_(None),
            )
            .order_by(Report.version_no.desc())
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def create_for_user(
        self,
        task_id: int,
        user_id: int,
        summary: str,
        result_json: dict,
        make_current: bool = True,
    ) -> Report:
        task_repository = AnalysisTaskRepository(self.session)
        task = await task_repository.get_for_user(
            task_id=task_id,
            user_id=user_id,
            for_update=True,
        )
        if task is None:
            raise LookupError("任务不存在或无权访问")

        if make_current:
            current_report_statement = (
                update(Report)
                .where(
                    Report.task_id == task_id,
                    Report.is_current.is_(True),
                    Report.deleted_at.is_(None),
                )
                .values(
                    is_current=False,
                    updated_at=func.now(),
                )
                .execution_options(synchronize_session="fetch")
            )
            await self.session.execute(current_report_statement)

        version_statement = select(
            func.coalesce(func.max(Report.version_no), 0) + 1
        ).where(Report.task_id == task_id)
        version_no = await self.session.scalar(version_statement)

        report = Report(
            task_id=task_id,
            version_no=version_no,
            is_current=make_current,
            summary=summary,
            result_json=result_json,
        )
        self.session.add(report)
        await self.session.flush()
        return report
