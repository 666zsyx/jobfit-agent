# 提供按用户隔离的分析任务数据访问。

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalysisTask


class AnalysisTaskRepository:
    """分析任务 Repository。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_user(
        self,
        task_id: int,
        user_id: int,
        for_update: bool = False,
    ) -> AnalysisTask | None:
        statement = select(AnalysisTask).where(
            AnalysisTask.task_id == task_id,
            AnalysisTask.user_id == user_id,
            AnalysisTask.deleted_at.is_(None),
        )

        if for_update:
            statement = statement.with_for_update()

        return await self.session.scalar(statement)

    async def list_for_user(
        self,
        user_id: int,
    ) -> list[AnalysisTask]:
        statement = (
            select(AnalysisTask)
            .where(
                AnalysisTask.user_id == user_id,
                AnalysisTask.deleted_at.is_(None),
            )
            .order_by(
                AnalysisTask.created_at.desc(),
                AnalysisTask.task_id.desc(),
            )
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def create(
        self,
        user_id: int,
        job_id: int,
        resume_version_id: int,
        conversation_id: int | None,
        max_steps: int = 8,
    ) -> AnalysisTask:
        task = AnalysisTask(
            user_id=user_id,
            job_id=job_id,
            resume_version_id=resume_version_id,
            conversation_id=conversation_id,
            status="pending",
            current_step=0,
            attempt=0,
            max_steps=max_steps,
        )
        self.session.add(task)
        await self.session.flush()
        return task

