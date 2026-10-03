# 真实验证关键词召回、向量召回和 RRF 混合排序。

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
from app.services.chunking import ingest_resume_version_chunks
from app.services.embeddings import FastEmbedEmbeddingProvider
from app.services.hybrid_search import search_resume_chunks_hybrid
from app.services.keyword_search import search_resume_chunks_by_keyword
from app.services.vector_index import ChromaVectorIndex
from app.services.vector_indexing import index_resume_version_chunks
from app.services.vector_search import search_resume_chunks_by_vector


async def check_hybrid_retrieval() -> None:
    suffix = uuid4().hex[:12]

    async with async_session_factory() as session:
        transaction = await session.begin()

        owner = User(
            username=f"hybrid-owner-{suffix}",
            email=f"hybrid-owner-{suffix}@example.com",
        )
        session.add(owner)
        await session.flush()

        resume = Resume(user_id=owner.user_id, title="STEP08 混合检索")
        session.add(resume)
        await session.flush()

        version = ResumeVersion(
            resume_id=resume.resume_id,
            version_no=1,
            raw_text="STEP08 hybrid source",
            extracted_sections={
                "sections": [
                    {
                        "section_type": "skills",
                        "title": "技能",
                        "content": (
                            "Python、FastAPI、PostgreSQL 17、Redis，"
                            "熟悉后端接口开发和数据库设计。"
                        ),
                    },
                    {
                        "section_type": "project_experience",
                        "title": "课程平台",
                        "content": (
                            "使用 FastAPI 开发课程接口，"
                            "负责 API 设计、权限校验和联调。"
                        ),
                    },
                    {
                        "section_type": "work_experience",
                        "title": "实习经历",
                        "content": (
                            "参与第三方 API 对接和接口联调，"
                            "记录请求参数与返回结果。"
                        ),
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

        await ingest_resume_version_chunks(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
        )

        provider = FastEmbedEmbeddingProvider(
            model_name=settings.embedding_model_name,
            cache_dir=settings.embedding_cache_path,
        )
        vector_index = ChromaVectorIndex(
            path=f".cache/chroma-hybrid-{suffix}",
            collection_name=f"jobfit_hybrid_{suffix}",
            model_name=provider.model_name,
            dimension=provider.dimension,
        )
        await index_resume_version_chunks(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            embedding_provider=provider,
            vector_index=vector_index,
        )

        requirement = "有 Python 后端接口开发经验"
        keyword_hits = await search_resume_chunks_by_keyword(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            requirement=requirement,
            top_k=10,
        )
        vector_hits = await search_resume_chunks_by_vector(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            requirement=requirement,
            top_k=10,
            embedding_provider=provider,
            vector_index=vector_index,
        )
        hybrid_hits = await search_resume_chunks_hybrid(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            requirement=requirement,
            top_k=10,
            top_n=5,
            embedding_provider=provider,
            vector_index=vector_index,
        )

        assert keyword_hits
        assert vector_hits
        assert hybrid_hits
        assert len({hit.chunk_id for hit in hybrid_hits}) == len(hybrid_hits)
        assert any(
            hit.lexical_rank is not None
            and hit.vector_rank is not None
            for hit in hybrid_hits
        )

        print(f"requirement: {requirement}")
        print(f"keyword hits: {len(keyword_hits)}")
        print(f"vector hits: {len(vector_hits)}")
        print(f"hybrid hits: {len(hybrid_hits)}")

        for hit in hybrid_hits:
            print(
                f"rank={hit.rank} "
                f"chunk_id={hit.chunk_id} "
                f"lexical_rank={hit.lexical_rank} "
                f"vector_rank={hit.vector_rank} "
                f"fusion={hit.fusion_score:.6f} "
                f"title={hit.title}"
            )

        print("deduplication: ok")
        print("rrf fusion: ok")

        await transaction.rollback()

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_hybrid_retrieval())
