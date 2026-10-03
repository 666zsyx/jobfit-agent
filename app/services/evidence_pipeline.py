# 实现 Rerank、EvidencePack 和 RRF 失败回退。

import asyncio
import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.knowledge import (
    EvidenceItem,
    EvidencePack,
    HybridSearchHit,
    RerankedSearchHit,
)
from app.services.embeddings import EmbeddingProvider
from app.services.hybrid_search import search_resume_chunks_hybrid
from app.services.reranking import Reranker
from app.services.vector_index import VectorIndex


DEFAULT_MIN_RERANK_SCORE = -2.9


def _hit_document(hit: HybridSearchHit) -> str:
    return f"{hit.title}\n{hit.content}"


def _common_evidence_fields(hit: HybridSearchHit) -> dict:
    return {
        "chunk_id": hit.chunk_id,
        "user_id": hit.user_id,
        "resume_version_id": hit.resume_version_id,
        "section_type": hit.section_type,
        "title": hit.title,
        "content": hit.content,
        "content_hash": hit.content_hash,
        "position": hit.position,
        "start_offset": hit.start_offset,
        "end_offset": hit.end_offset,
        "chunker_version": hit.chunker_version,
    }


async def rerank_hybrid_hits(
    *,
    requirement: str,
    hybrid_hits: list[HybridSearchHit],
    reranker: Reranker,
) -> list[RerankedSearchHit]:
    """使用 Cross-Encoder 对混合候选重新打分。"""

    if not requirement.strip():
        raise ValueError("requirement 不能为空")

    if not hybrid_hits:
        return []

    documents = [_hit_document(hit) for hit in hybrid_hits]
    scores = await asyncio.to_thread(
        reranker.score,
        query=requirement,
        documents=documents,
    )

    if len(scores) != len(hybrid_hits):
        raise RuntimeError("Reranker 返回的分数数量不匹配")

    if any(not math.isfinite(score) for score in scores):
        raise RuntimeError("Reranker 返回了非有限分数")

    scored_hits = list(zip(hybrid_hits, scores, strict=True))
    scored_hits.sort(
        key=lambda item: (
            -item[1],
            item[0].rank,
            item[0].position,
            item[0].chunk_id,
        )
    )

    return [
        RerankedSearchHit(
            **_common_evidence_fields(hit),
            lexical_score=hit.lexical_score,
            lexical_rank=hit.lexical_rank,
            vector_score=hit.vector_score,
            vector_rank=hit.vector_rank,
            fusion_score=hit.fusion_score,
            rank=hit.rank,
            rerank_score=round(score, 8),
            rerank_rank=rank,
        )
        for rank, (hit, score) in enumerate(
            scored_hits,
            start=1,
        )
    ]


def build_evidence_pack_from_reranked(
    *,
    requirement: str,
    reranked_hits: list[RerankedSearchHit],
    top_n: int,
    min_rerank_score: float = DEFAULT_MIN_RERANK_SCORE,
) -> EvidencePack:
    if top_n < 1:
        raise ValueError("top_n 必须大于等于 1")

    accepted_hits = [
        hit
        for hit in reranked_hits
        if hit.rerank_score >= min_rerank_score
    ]

    return EvidencePack(
        requirement=requirement.strip(),
        items=[
            EvidenceItem(
                **_common_evidence_fields(hit),
                relevance_score=hit.rerank_score,
                rank=rank,
            )
            for rank, hit in enumerate(
                accepted_hits[:top_n],
                start=1,
            )
        ],
        rerank_applied=True,
    )


def build_evidence_pack_from_hybrid(
    *,
    requirement: str,
    hybrid_hits: list[HybridSearchHit],
    top_n: int,
    fallback_reason: str,
) -> EvidencePack:
    if top_n < 1:
        raise ValueError("top_n 必须大于等于 1")

    return EvidencePack(
        requirement=requirement.strip(),
        items=[
            EvidenceItem(
                **_common_evidence_fields(hit),
                relevance_score=hit.fusion_score,
                rank=rank,
            )
            for rank, hit in enumerate(
                hybrid_hits[:top_n],
                start=1,
            )
        ],
        rerank_applied=False,
        degraded=True,
        fallback_reason=fallback_reason,
    )


async def search_resume_chunks_with_evidence(
    session: AsyncSession,
    *,
    user_id: int,
    resume_version_id: int,
    requirement: str,
    candidate_top_k: int,
    rerank_candidate_top_n: int,
    evidence_top_n: int,
    min_rerank_score: float = DEFAULT_MIN_RERANK_SCORE,
    embedding_provider: EmbeddingProvider,
    vector_index: VectorIndex,
    reranker: Reranker,
) -> EvidencePack:
    """执行混合召回、Rerank 和 EvidencePack 构建。"""

    hybrid_hits = await search_resume_chunks_hybrid(
        session,
        user_id=user_id,
        resume_version_id=resume_version_id,
        requirement=requirement,
        top_k=candidate_top_k,
        top_n=rerank_candidate_top_n,
        embedding_provider=embedding_provider,
        vector_index=vector_index,
    )

    if not hybrid_hits:
        return EvidencePack(
            requirement=requirement.strip(),
            items=[],
            rerank_applied=False,
        )

    try:
        reranked_hits = await rerank_hybrid_hits(
            requirement=requirement,
            hybrid_hits=hybrid_hits,
            reranker=reranker,
        )
    except Exception:
        return build_evidence_pack_from_hybrid(
            requirement=requirement,
            hybrid_hits=hybrid_hits,
            top_n=evidence_top_n,
            fallback_reason="reranker_unavailable",
        )

    return build_evidence_pack_from_reranked(
        requirement=requirement,
        reranked_hits=reranked_hits,
        top_n=evidence_top_n,
        min_rerank_score=min_rerank_score,
    )
