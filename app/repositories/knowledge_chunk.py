# 提供按用户隔离的知识 Chunk 数据访问。

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeChunk, Resume, ResumeVersion


class KnowledgeChunkRepository:
    """知识 Chunk Repository。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_user(
        self,
        chunk_id: int,
        user_id: int,
    ) -> KnowledgeChunk | None:
        statement = select(KnowledgeChunk).where(
            KnowledgeChunk.chunk_id == chunk_id,
            KnowledgeChunk.user_id == user_id,
        )
        return await self.session.scalar(statement)

    async def list_for_resume_version(
        self,
        *,
        user_id: int,
        resume_version_id: int,
        chunker_version: str = "v1",
        index_status: str | None = None,
    ) -> list[KnowledgeChunk]:
        statement = select(KnowledgeChunk).where(
            KnowledgeChunk.user_id == user_id,
            KnowledgeChunk.resume_version_id == resume_version_id,
            KnowledgeChunk.chunker_version == chunker_version,
        )

        if index_status is not None:
            statement = statement.where(
                KnowledgeChunk.index_status == index_status
            )

        statement = statement.order_by(KnowledgeChunk.position)
        result = await self.session.scalars(statement)
        return list(result.all())

    async def create_for_user(
        self,
        *,
        user_id: int,
        resume_version_id: int,
        section_type: str,
        title: str,
        content: str,
        content_hash: str,
        position: int,
        start_offset: int | None = None,
        end_offset: int | None = None,
        chunker_version: str = "v1",
        index_status: str = "pending",
        embedding_model: str | None = None,
        embedding_dimension: int | None = None,
    ) -> KnowledgeChunk:
        # 锁定父简历，防止校验通过后简历被并发软删除。
        parent_statement = (
            select(ResumeVersion.resume_version_id)
            .join(
                Resume,
                ResumeVersion.resume_id == Resume.resume_id,
            )
            .where(
                ResumeVersion.resume_version_id == resume_version_id,
                Resume.user_id == user_id,
                Resume.deleted_at.is_(None),
            )
            .with_for_update()
        )
        parent_resume_version_id = await self.session.scalar(
            parent_statement
        )

        if parent_resume_version_id is None:
            raise LookupError("简历版本不存在或无权访问")

        chunk = KnowledgeChunk(
            user_id=user_id,
            resume_version_id=resume_version_id,
            section_type=section_type,
            title=title,
            content=content,
            content_hash=content_hash,
            position=position,
            start_offset=start_offset,
            end_offset=end_offset,
            chunker_version=chunker_version,
            index_status=index_status,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
        )
        self.session.add(chunk)
        await self.session.flush()
        return chunk
