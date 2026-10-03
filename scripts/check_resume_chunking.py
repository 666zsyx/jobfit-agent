# 在可回滚事务中验证简历 Chunking、幂等摄入和 stale 标记。

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import KnowledgeChunk, Resume, ResumeVersion, User
from app.db.session import async_session_factory, dispose_engine
from app.repositories import KnowledgeChunkRepository
from app.services.chunking import ingest_resume_version_chunks


async def check_resume_chunking() -> None:
    suffix = uuid4().hex[:12]

    async with async_session_factory() as session:
        transaction = await session.begin()

        owner = User(
            username=f"chunk-owner-{suffix}",
            email=f"chunk-owner-{suffix}@example.com",
        )
        other_user = User(
            username=f"chunk-other-{suffix}",
            email=f"chunk-other-{suffix}@example.com",
        )
        session.add_all([owner, other_user])
        await session.flush()

        resume = Resume(user_id=owner.user_id, title="STEP08 Chunk 测试")
        session.add(resume)
        await session.flush()

        extracted_sections = {
            "sections": [
                {
                    "section_type": "skills",
                    "title": "技能",
                    "content": "Python、FastAPI、PostgreSQL。",
                },
                {
                    "section_type": "project_experience",
                    "title": "项目经历",
                    "content": "使用 FastAPI 开发课程接口。" * 120,
                },
            ]
        }
        version = ResumeVersion(
            resume_id=resume.resume_id,
            version_no=1,
            raw_text="STEP08 chunk source",
            extracted_sections=extracted_sections,
        )
        session.add(version)
        await session.flush()

        chunk_repository = KnowledgeChunkRepository(session)

        stale_candidate = await chunk_repository.create_for_user(
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            section_type="other",
            title="旧 Chunk",
            content="这段内容将在重新摄入后标记 stale。",
            content_hash=f"stale-{suffix}",
            position=999,
        )

        first_chunks = await ingest_resume_version_chunks(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
        )
        assert len(first_chunks) > 2

        first_ids = [chunk.chunk_id for chunk in first_chunks]
        first_positions = [chunk.position for chunk in first_chunks]

        await chunk_repository.mark_index_status_for_user(
            chunk_id=first_chunks[0].chunk_id,
            user_id=owner.user_id,
            index_status="indexed",
            embedding_model="fake-embedding",
            embedding_dimension=3,
        )

        second_chunks = await ingest_resume_version_chunks(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
        )
        second_ids = [chunk.chunk_id for chunk in second_chunks]
        second_positions = [chunk.position for chunk in second_chunks]

        assert second_ids == first_ids
        assert second_positions == first_positions
        assert second_chunks[0].index_status == "indexed"
        assert second_chunks[0].embedding_model == "fake-embedding"

        await session.refresh(stale_candidate)
        stale_chunk = await chunk_repository.get_for_user(
            chunk_id=stale_candidate.chunk_id,
            user_id=owner.user_id,
        )
        assert stale_chunk is not None
        assert stale_chunk.index_status == "stale"

        try:
            await ingest_resume_version_chunks(
                session,
                user_id=other_user.user_id,
                resume_version_id=version.resume_version_id,
            )
        except LookupError:
            print("cross-user ingestion rejected: ok")
        else:
            raise AssertionError("跨用户摄入未被拒绝")

        print(f"chunk count: {len(first_chunks)}")
        print(f"positions: {first_positions}")
        print("idempotent ingestion: ok")
        print("indexed status preserved: ok")
        print("stale old chunk: ok")

        await transaction.rollback()

    async with async_session_factory() as session:
        remaining = await session.scalar(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.content_hash.like(f"stale-{suffix}"))
            .limit(1)
        )
        assert remaining is None
        print("rollback cleanup: ok")

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_resume_chunking())

