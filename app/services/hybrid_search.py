# 实现关键词与向量召回的 RRF 混合排序。

import asyncio
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.knowledge import (
    HybridSearchHit,
    LexicalSearchHit,
    RetrievalHit,
    VectorSearchHit,
)
from app.services.embeddings import EmbeddingProvider
from app.services.keyword_search import search_resume_chunks_by_keyword
from app.services.vector_index import VectorIndex
from app.services.vector_search import search_resume_chunks_by_vector


DEFAULT_RRF_K = 60
DEFAULT_KEYWORD_WEIGHT = 1.0
DEFAULT_VECTOR_WEIGHT = 1.0


@dataclass
class _FusionCandidate:
    base: RetrievalHit
    lexical_score: float | None = None
    lexical_rank: int | None = None
    vector_score: float | None = None
    vector_rank: int | None = None
    fusion_score: float = 0.0

    def add_keyword(
        self,
        hit: LexicalSearchHit,
        *,
        rrf_k: int,
        weight: float,
    ) -> None:
        self.lexical_score = hit.bm25_score
        self.lexical_rank = hit.rank
        self.fusion_score += weight / (rrf_k + hit.rank)

    def add_vector(
        self,
        hit: VectorSearchHit,
        *,
        rrf_k: int,
        weight: float,
    ) -> None:
        self.vector_score = hit.similarity
        self.vector_rank = hit.rank
        self.fusion_score += weight / (rrf_k + hit.rank)


def _add_candidate(
    candidates: dict[int, _FusionCandidate],
    hit: RetrievalHit,
) -> _FusionCandidate:
    existing = candidates.get(hit.chunk_id)

    if existing is None:
        candidate = _FusionCandidate(base=hit)
        candidates[hit.chunk_id] = candidate
        return candidate

    if existing.base.content_hash != hit.content_hash:
        raise ValueError("同一 chunk_id 的内容哈希不一致")

    return existing


def fuse_retrieval_hits(
    *,
    keyword_hits: list[LexicalSearchHit],
    vector_hits: list[VectorSearchHit],
    rrf_k: int = DEFAULT_RRF_K,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
    vector_weight: float = DEFAULT_VECTOR_WEIGHT,
    top_n: int = 10,
) -> list[HybridSearchHit]:
    """使用 RRF 按排名融合两路召回，不直接相加原始分数。"""

    if rrf_k < 1:
        raise ValueError("rrf_k 必须大于等于 1")

    if keyword_weight < 0 or vector_weight < 0:
        raise ValueError("召回权重不能小于 0")

    if keyword_weight == 0 and vector_weight == 0:
        raise ValueError("至少一个召回权重必须大于 0")

    if top_n < 1:
        raise ValueError("top_n 必须大于等于 1")

    candidates: dict[int, _FusionCandidate] = {}

    for hit in keyword_hits:
        candidate = _add_candidate(candidates, hit)
        candidate.add_keyword(
            hit,
            rrf_k=rrf_k,
            weight=keyword_weight,
        )

    for hit in vector_hits:
        candidate = _add_candidate(candidates, hit)
        candidate.add_vector(
            hit,
            rrf_k=rrf_k,
            weight=vector_weight,
        )

    ranked_candidates = sorted(
        candidates.values(),
        key=lambda candidate: (
            -candidate.fusion_score,
            min(
                rank
                for rank in (
                    candidate.lexical_rank,
                    candidate.vector_rank,
                )
                if rank is not None
            ),
            candidate.base.position,
            candidate.base.chunk_id,
        ),
    )[:top_n]

    return [
        HybridSearchHit(
            chunk_id=candidate.base.chunk_id,
            user_id=candidate.base.user_id,
            resume_version_id=candidate.base.resume_version_id,
            section_type=candidate.base.section_type,
            title=candidate.base.title,
            content=candidate.base.content,
            content_hash=candidate.base.content_hash,
            position=candidate.base.position,
            start_offset=candidate.base.start_offset,
            end_offset=candidate.base.end_offset,
            chunker_version=candidate.base.chunker_version,
            lexical_score=candidate.lexical_score,
            lexical_rank=candidate.lexical_rank,
            vector_score=candidate.vector_score,
            vector_rank=candidate.vector_rank,
            fusion_score=round(candidate.fusion_score, 8),
            rank=rank,
        )
        for rank, candidate in enumerate(
            ranked_candidates,
            start=1,
        )
    ]


async def search_resume_chunks_hybrid(
    session: AsyncSession,
    *,
    user_id: int,
    resume_version_id: int,
    requirement: str,
    top_k: int,
    top_n: int,
    embedding_provider: EmbeddingProvider,
    vector_index: VectorIndex,
    rrf_k: int = DEFAULT_RRF_K,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
    vector_weight: float = DEFAULT_VECTOR_WEIGHT,
) -> list[HybridSearchHit]:
    """并行执行关键词和向量召回，再使用 RRF 融合。"""

    if top_k < 1:
        raise ValueError("top_k 必须大于等于 1")

    keyword_hits, vector_hits = await asyncio.gather(
        search_resume_chunks_by_keyword(
            session,
            user_id=user_id,
            resume_version_id=resume_version_id,
            requirement=requirement,
            top_k=top_k,
        ),
        search_resume_chunks_by_vector(
            session,
            user_id=user_id,
            resume_version_id=resume_version_id,
            requirement=requirement,
            top_k=top_k,
            embedding_provider=embedding_provider,
            vector_index=vector_index,
        ),
    )

    return fuse_retrieval_hits(
        keyword_hits=keyword_hits,
        vector_hits=vector_hits,
        rrf_k=rrf_k,
        keyword_weight=keyword_weight,
        vector_weight=vector_weight,
        top_n=top_n,
    )
