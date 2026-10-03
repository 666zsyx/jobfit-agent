# 真实验证 Rerank、EvidencePack、引用校验和失败回退。

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
from app.services.citation_validation import validate_evidence_citations
from app.services.embeddings import FastEmbedEmbeddingProvider
from app.services.evidence_pipeline import (
    search_resume_chunks_with_evidence,
)
from app.services.hybrid_search import search_resume_chunks_hybrid
from app.services.reranking import FastEmbedReranker
from app.services.vector_index import ChromaVectorIndex
from app.services.vector_indexing import index_resume_version_chunks


class FailingReranker:
    model_name = "failing-reranker"

    def score(self, *, query: str, documents: list[str]) -> list[float]:
        raise RuntimeError("forced reranker failure")


async def check_rerank_evidence() -> None:
    suffix = uuid4().hex[:12]

    async with async_session_factory() as session:
        transaction = await session.begin()

        owner = User(
            username=f"rerank-owner-{suffix}",
            email=f"rerank-owner-{suffix}@example.com",
        )
        session.add(owner)
        await session.flush()

        resume = Resume(user_id=owner.user_id, title="STEP08 Rerank")
        session.add(resume)
        await session.flush()

        version = ResumeVersion(
            resume_id=resume.resume_id,
            version_no=1,
            raw_text="STEP08 rerank source",
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
            path=f".cache/chroma-rerank-{suffix}",
            collection_name=f"jobfit_rerank_{suffix}",
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

        reranker = FastEmbedReranker(
            model_name=settings.reranker_model_name,
            cache_dir=settings.embedding_cache_path,
        )
        evidence_pack = await search_resume_chunks_with_evidence(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            requirement=requirement,
            candidate_top_k=10,
            rerank_candidate_top_n=5,
            evidence_top_n=3,
            embedding_provider=provider,
            vector_index=vector_index,
            reranker=reranker,
        )

        assert evidence_pack.rerank_applied is True
        assert evidence_pack.degraded is False
        assert evidence_pack.items
        assert len(evidence_pack.items) <= 3

        known_ids = [item.chunk_id for item in evidence_pack.items]
        valid_citation = validate_evidence_citations(
            evidence_pack=evidence_pack,
            cited_chunk_ids=known_ids[:1],
        )
        invalid_citation = validate_evidence_citations(
            evidence_pack=evidence_pack,
            cited_chunk_ids=[999999],
        )

        assert valid_citation.valid is True
        assert invalid_citation.valid is False
        assert invalid_citation.unknown_chunk_ids == [999999]

        fallback_pack = await search_resume_chunks_with_evidence(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
            requirement=requirement,
            candidate_top_k=10,
            rerank_candidate_top_n=5,
            evidence_top_n=3,
            embedding_provider=provider,
            vector_index=vector_index,
            reranker=FailingReranker(),
        )
        assert fallback_pack.rerank_applied is False
        assert fallback_pack.degraded is True
        assert fallback_pack.fallback_reason == "reranker_unavailable"
        assert fallback_pack.items

        print("hybrid order:")
        for hit in hybrid_hits:
            print(
                f"  rank={hit.rank} chunk_id={hit.chunk_id} "
                f"title={hit.title}"
            )

        print("reranked evidence pack:")
        for item in evidence_pack.items:
            print(
                f"  rank={item.rank} chunk_id={item.chunk_id} "
                f"score={item.relevance_score:.4f} title={item.title}"
            )

        print("citation validation: ok")
        print("reranker fallback: ok")

        await transaction.rollback()

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_rerank_evidence())
