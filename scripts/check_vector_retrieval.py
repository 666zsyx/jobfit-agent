# 真实验证 Embedding、Chroma 向量召回和用户隔离。

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.db.models import Resume, ResumeVersion, User
from app.db.session import async_session_factory, dispose_engine
from app.repositories import KnowledgeChunkRepository
from app.services.chunking import ingest_resume_version_chunks
from app.services.embeddings import FastEmbedEmbeddingProvider
from app.services.vector_index import ChromaVectorIndex
from app.services.vector_indexing import (
    index_resume_version_chunks,
    rebuild_resume_version_index,
)
from app.services.vector_search import search_resume_chunks_by_vector


async def check_vector_retrieval() -> None:
    suffix = uuid4().hex[:12]

    async with async_session_factory() as session:
        transaction = await session.begin()

        owner = User(
            username=f"vector-owner-{suffix}",
            email=f"vector-owner-{suffix}@example.com",
        )
        other_user = User(
            username=f"vector-other-{suffix}",
            email=f"vector-other-{suffix}@example.com",
        )
        session.add_all([owner, other_user])
        await session.flush()

        resume = Resume(user_id=owner.user_id, title="STEP08 向量测试")
        session.add(resume)
        await session.flush()

        version = ResumeVersion(
            resume_id=resume.resume_id,
            version_no=1,
            raw_text="STEP08 vector source",
            extracted_sections={
                "sections": [
                    {
                        "section_type": "skills",
                        "title": "技能",
                        "content": (
                            "Python、FastAPI、PostgreSQL、Redis，"
                            "熟悉后端接口开发和数据库设计。"
                        ),
                    },
                    {
                        "section_type": "project_experience",
                        "title": "课程平台",
                        "content": (
                            "使用 FastAPI 开发课程接口，"
                            "负责接口设计、权限校验和联调。"
                        ),
                    },
                    {
                        "section_type": "education",
                        "title": "教育经历",
                        "content": "某大学计算机科学与技术专业。",
                    },
                    {
                        "section_type": "other",
                        "title": "其他技能",
                        "content": "了解 Rust 和 C++，主要参加算法课程练习。",
                    },
                ]
            },
        )
        session.add(version)
        await session.flush()

        chunks = await ingest_resume_version_chunks(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
        )
        assert chunks

        provider = FastEmbedEmbeddingProvider(
            model_name=settings.embedding_model_name,
            cache_dir=settings.embedding_cache_path,
        )
        vector_index = ChromaVectorIndex(
            path=f".cache/chroma-check-{suffix}",
            collection_name=f"jobfit_check_{suffix}",
            model_name=provider.model_name,
            dimension=provider.dimension,
        )

        indexed_ids = await index_resume_version_chunks(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            embedding_provider=provider,
            vector_index=vector_index,
        )
        assert sorted(indexed_ids) == sorted(
            chunk.chunk_id for chunk in chunks
        )

        results = await search_resume_chunks_by_vector(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            requirement="有 Python 后端接口开发经验",
            top_k=3,
            embedding_provider=provider,
            vector_index=vector_index,
        )
        assert results
        assert any(
            "Python" in result.content or "FastAPI" in result.content
            for result in results
        )

        other_user_results = await search_resume_chunks_by_vector(
            session,
            user_id=other_user.user_id,
            resume_version_id=version.resume_version_id,
            requirement="有 Python 后端接口开发经验",
            top_k=3,
            embedding_provider=provider,
            vector_index=vector_index,
        )
        assert other_user_results == []

        chunk_repository = KnowledgeChunkRepository(session)
        indexed_chunks = await chunk_repository.list_for_resume_version(
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
        )
        assert all(
            chunk.index_status == "indexed"
            for chunk in indexed_chunks
        )

        print(f"model: {provider.model_name}")
        print(f"dimension: {provider.dimension}")
        print(f"indexed chunks: {len(indexed_ids)}")

        for result in results:
            print(
                f"rank={result.rank} "
                f"similarity={result.similarity:.4f} "
                f"chunk_id={result.chunk_id} "
                f"title={result.title}"
            )

        print("cross-user vector filter: ok")
        print("index status: ok")

        rebuilt_ids = await rebuild_resume_version_index(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            embedding_provider=provider,
            vector_index=vector_index,
        )
        assert sorted(rebuilt_ids) == sorted(indexed_ids)

        rebuilt_results = await search_resume_chunks_by_vector(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            requirement="有 Python 后端接口开发经验",
            top_k=3,
            embedding_provider=provider,
            vector_index=vector_index,
        )
        assert rebuilt_results
        print("vector index rebuild: ok")

        await transaction.rollback()

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_vector_retrieval())


