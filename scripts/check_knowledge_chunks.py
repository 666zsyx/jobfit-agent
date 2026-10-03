# 在可回滚事务中验证 KnowledgeChunk 持久化和用户隔离。

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import (
    KnowledgeChunk,
    Resume,
    ResumeVersion,
    User,
)
from app.db.session import async_session_factory, dispose_engine
from app.repositories import KnowledgeChunkRepository


async def check_knowledge_chunks() -> None:
    suffix = uuid4().hex[:12]
    content_hash = f"step08-{suffix}"

    async with async_session_factory() as session:
        transaction = await session.begin()

        owner = User(
            username=f"step08-owner-{suffix}",
            email=f"step08-owner-{suffix}@example.com",
        )
        other_user = User(
            username=f"step08-other-{suffix}",
            email=f"step08-other-{suffix}@example.com",
        )
        session.add_all([owner, other_user])
        await session.flush()

        resume = Resume(user_id=owner.user_id, title="STEP08 测试简历")
        session.add(resume)
        await session.flush()

        version = ResumeVersion(
            resume_id=resume.resume_id,
            version_no=1,
            raw_text="Python、FastAPI、PostgreSQL",
            extracted_sections={"sections": []},
        )
        session.add(version)
        await session.flush()

        repository = KnowledgeChunkRepository(session)

        chunk = await repository.create_for_user(
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            section_type="skills",
            title="技能",
            content="Python、FastAPI、PostgreSQL",
            content_hash=content_hash,
            position=1,
            start_offset=0,
            end_offset=27,
        )

        chunks = await repository.list_for_resume_version(
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
        )
        own_chunk = await repository.get_for_user(
            chunk_id=chunk.chunk_id,
            user_id=owner.user_id,
        )
        other_chunk = await repository.get_for_user(
            chunk_id=chunk.chunk_id,
            user_id=other_user.user_id,
        )

        assert len(chunks) == 1
        assert own_chunk is not None
        assert own_chunk.content == "Python、FastAPI、PostgreSQL"
        assert other_chunk is None

        upserted = await repository.upsert_for_user(
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            section_type="skills",
            title="技能",
            content="Python、FastAPI、PostgreSQL、Redis",
            content_hash=f"{content_hash}-updated",
            position=1,
            start_offset=0,
            end_offset=34,
        )
        assert upserted.chunk_id == chunk.chunk_id

        chunks = await repository.list_for_resume_version(
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
        )
        assert len(chunks) == 1
        assert chunks[0].content.endswith("Redis")

        indexed = await repository.mark_index_status_for_user(
            chunk_id=chunk.chunk_id,
            user_id=owner.user_id,
            index_status="indexed",
            embedding_model="fake-embedding",
            embedding_dimension=3,
        )
        assert indexed.index_status == "indexed"
        assert indexed.embedding_model == "fake-embedding"
        assert indexed.embedding_dimension == 3

        try:
            await repository.mark_index_status_for_user(
                chunk_id=chunk.chunk_id,
                user_id=other_user.user_id,
                index_status="indexed",
            )
        except LookupError:
            print("cross-user status update rejected: ok")
        else:
            raise AssertionError("跨用户状态更新未被拒绝")

        try:
            await repository.create_for_user(
                user_id=other_user.user_id,
                resume_version_id=version.resume_version_id,
                section_type="skills",
                title="越权技能",
                content="不应写入",
                content_hash=f"forbidden-{suffix}",
                position=2,
                chunker_version="forbidden",
            )
        except LookupError:
            print("cross-user write rejected: ok")
        else:
            raise AssertionError("跨用户写入未被拒绝")

        print(
            "created: "
            f"chunk_id={chunk.chunk_id} "
            f"user_id={chunk.user_id} "
            f"resume_version_id={chunk.resume_version_id} "
            f"position={chunk.position}"
        )
        print(f"list count: {len(chunks)}")
        print("cross-user read: ok")
        print("transaction rollback next")

        await transaction.rollback()

    async with async_session_factory() as session:
        remaining = await session.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.content_hash == content_hash)
        )
        assert remaining == 0
        print("rollback cleanup: ok")

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_knowledge_chunks())
