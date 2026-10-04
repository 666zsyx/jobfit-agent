# 提供按用户隔离的岗位数据访问。

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job


class JobRepository:
    """岗位 Repository。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_user(
        self,
        job_id: int,
        user_id: int,
        for_update: bool = False,
    ) -> Job | None:
        statement = select(Job).where(
            Job.job_id == job_id,
            Job.user_id == user_id,
            Job.deleted_at.is_(None),
        )

        if for_update:
            statement = statement.with_for_update()

        return await self.session.scalar(statement)

    async def list_for_user(
        self,
        user_id: int,
    ) -> list[Job]:
        statement = (
            select(Job)
            .where(
                Job.user_id == user_id,
                Job.deleted_at.is_(None),
            )
            .order_by(
                Job.created_at.desc(),
                Job.job_id.desc(),
            )
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def create(
        self,
        user_id: int,
        raw_description: str,
        title: str | None = None,
        company_name: str | None = None,
        extracted_requirements: dict | None = None,
    ) -> Job:
        job = Job(
            user_id=user_id,
            title=title,
            company_name=company_name,
            raw_description=raw_description,
            extracted_requirements=extracted_requirements,
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def update(
        self,
        job: Job,
        **values: object,
    ) -> Job:
        for field, value in values.items():
            setattr(job, field, value)

        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def soft_delete(self, job: Job) -> Job:
        job.status = "archived"
        job.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(job)
        return job
