# 提供按用户隔离的简历版本数据访问。

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Resume, ResumeVersion


class ResumeVersionRepository:
    """简历版本 Repository。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_user(
        self,
        resume_version_id: int,
        user_id: int,
        for_update: bool = False,
    ) -> ResumeVersion | None:
        statement = (
            select(ResumeVersion)
            .join(
                Resume,
                ResumeVersion.resume_id == Resume.resume_id,
            )
            .where(
                ResumeVersion.resume_version_id == resume_version_id,
                Resume.user_id == user_id,
                Resume.deleted_at.is_(None),
            )
        )

        if for_update:
            statement = statement.with_for_update()

        return await self.session.scalar(statement)

    async def create_for_user(
        self,
        resume_id: int,
        user_id: int,
        version_no: int,
        raw_text: str,
        extracted_sections: dict | None = None,
        source_type: str = "text",
    ) -> ResumeVersion:
        # 锁住父简历行，避免校验通过后父简历被并发软删除。
        parent_statement = (
            select(Resume.resume_id)
            .where(
                Resume.resume_id == resume_id,
                Resume.user_id == user_id,
                Resume.deleted_at.is_(None),
            )
            .with_for_update()
        )
        parent_resume_id = await self.session.scalar(parent_statement)

        if parent_resume_id is None:
            raise LookupError("简历不存在或无权访问")

        resume_version = ResumeVersion(
            resume_id=resume_id,
            version_no=version_no,
            raw_text=raw_text,
            extracted_sections=extracted_sections,
            source_type=source_type,
        )
        self.session.add(resume_version)
        await self.session.flush()
        return resume_version


