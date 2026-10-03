# 提供按用户隔离的知识 Chunk 数据访问。

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeChunk, Resume, ResumeVersion


class KnowledgeChunkRepository:
    """知识 Chunk Repository。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _lock_parent_resume_version(
        self,
        *,
        user_id: int,
        resume_version_id: int,
    ) -> int:
        """锁定并验证简历版本属于当前用户。"""

        statement = (
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
        parent_resume_version_id = await self.session.scalar(statement)

        if parent_resume_version_id is None:
            raise LookupError("简历版本不存在或无权访问")

        return parent_resume_version_id

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
        await self._lock_parent_resume_version(
            user_id=user_id,
            resume_version_id=resume_version_id,
        )

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

    async def upsert_for_user(
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
    ) -> KnowledgeChunk:
        """按版本身份幂等写入 Chunk，供后续重建流程复用。"""

        await self._lock_parent_resume_version(
            user_id=user_id,
            resume_version_id=resume_version_id,
        )

        statement = select(KnowledgeChunk).where(
            KnowledgeChunk.user_id == user_id,
            KnowledgeChunk.resume_version_id == resume_version_id,
            KnowledgeChunk.chunker_version == chunker_version,
            KnowledgeChunk.position == position,
        )
        chunk = await self.session.scalar(statement)

        if chunk is None:
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
            )
            self.session.add(chunk)
        else:
            chunk.section_type = section_type
            chunk.title = title
            chunk.content = content
            chunk.content_hash = content_hash
            chunk.start_offset = start_offset
            chunk.end_offset = end_offset
            chunk.index_status = index_status

        await self.session.flush()
        return chunk

    async def mark_index_status_for_user(
        self,
        *,
        chunk_id: int,
        user_id: int,
        index_status: str,
        embedding_model: str | None = None,
        embedding_dimension: int | None = None,
    ) -> KnowledgeChunk:
        chunk = await self.get_for_user(
            chunk_id=chunk_id,
            user_id=user_id,
        )

        if chunk is None:
            raise LookupError("知识 Chunk 不存在或无权访问")

        chunk.index_status = index_status
        chunk.embedding_model = embedding_model
        chunk.embedding_dimension = embedding_dimension
        await self.session.flush()
        return chunk
