# 提供按用户隔离的简历数据访问。

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Resume


class ResumeRepository:
    """简历 Repository。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_user(
        self,
        resume_id: int,
        user_id: int,
        with_versions: bool = False,
    ) -> Resume | None:
        statement = select(Resume).where(
            Resume.resume_id == resume_id,
            Resume.user_id == user_id,
            Resume.deleted_at.is_(None),
        )

        if with_versions:
            statement = statement.options(
                selectinload(Resume.versions)
            )

        return await self.session.scalar(statement)

    async def list_for_user(
        self,
        user_id: int,
    ) -> list[Resume]:
        statement = (
            select(Resume)
            .where(
                Resume.user_id == user_id,
                Resume.deleted_at.is_(None),
            )
            .order_by(
                Resume.created_at.desc(),
                Resume.resume_id.desc(),
            )
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def create(
        self,
        user_id: int,
        title: str,
    ) -> Resume:
        resume = Resume(
            user_id=user_id,
            title=title,
        )
        self.session.add(resume)
        await self.session.flush()
        return resume
