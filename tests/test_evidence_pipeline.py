# 验证 Rerank、EvidencePack 和引用校验。

import pytest

from app.schemas.knowledge import (
    EvidencePack,
    HybridSearchHit,
    RerankedSearchHit,
)
from app.services.citation_validation import (
    validate_evidence_citations,
    validate_report_citations,
)
from app.services.evidence_pipeline import (
    build_evidence_pack_from_hybrid,
    build_evidence_pack_from_reranked,
    rerank_hybrid_hits,
)


class FakeReranker:
    model_name = "fake-reranker"

    def __init__(self, scores: dict[int, float]) -> None:
        self.scores = scores

    def score(self, *, query: str, documents: list[str]) -> list[float]:
        return [
            self.scores[index]
            for index in range(1, len(documents) + 1)
        ]


def make_hybrid_hit(
    chunk_id: int,
    *,
    rank: int,
    fusion_score: float,
) -> HybridSearchHit:
    return HybridSearchHit(
        chunk_id=chunk_id,
        user_id=10,
        resume_version_id=1001,
        section_type="project_experience",
        title=f"项目 {chunk_id}",
        content=f"项目内容 {chunk_id}",
        content_hash=str(chunk_id) * 64,
        position=chunk_id,
        start_offset=0,
        end_offset=10,
        chunker_version="v1",
        lexical_score=1.0,
        lexical_rank=rank,
        vector_score=0.8,
        vector_rank=rank,
        fusion_score=fusion_score,
        rank=rank,
    )


@pytest.mark.anyio
async def test_rerank_reorders_hybrid_candidates():
    hits = [
        make_hybrid_hit(1, rank=1, fusion_score=0.03),
        make_hybrid_hit(2, rank=2, fusion_score=0.02),
    ]
    reranker = FakeReranker({1: 0.2, 2: 0.9})

    reranked = await rerank_hybrid_hits(
        requirement="Python 后端开发",
        hybrid_hits=hits,
        reranker=reranker,
    )

    assert [hit.chunk_id for hit in reranked] == [2, 1]
    assert reranked[0].rerank_rank == 1
    assert reranked[0].rerank_score == 0.9


def test_build_evidence_pack_keeps_top_n():
    hits = [
        make_hybrid_hit(1, rank=1, fusion_score=0.03),
        make_hybrid_hit(2, rank=2, fusion_score=0.02),
    ]

    pack = build_evidence_pack_from_hybrid(
        requirement="Python 后端开发",
        hybrid_hits=hits,
        top_n=1,
        fallback_reason="reranker_unavailable",
    )

    assert isinstance(pack, EvidencePack)
    assert [item.chunk_id for item in pack.items] == [1]
    assert pack.rerank_applied is False
    assert pack.degraded is True


def test_build_evidence_pack_from_reranked_marks_applied():
    hits = [
        make_hybrid_hit(1, rank=1, fusion_score=0.03),
    ]
    reranked = hits[0].model_dump()
    reranked["rerank_score"] = 0.8
    reranked["rerank_rank"] = 1

    from app.schemas.knowledge import RerankedSearchHit

    pack = build_evidence_pack_from_reranked(
        requirement="Python 后端开发",
        reranked_hits=[RerankedSearchHit.model_validate(reranked)],
        top_n=1,
    )

    assert pack.rerank_applied is True
    assert pack.items[0].relevance_score == 0.8


def test_evidence_pack_filters_below_production_threshold():
    hit_data = make_hybrid_hit(
        1,
        rank=1,
        fusion_score=0.03,
    ).model_dump()
    hit_data["rerank_score"] = -3.5
    hit_data["rerank_rank"] = 1

    pack = build_evidence_pack_from_reranked(
        requirement="Rust 经验",
        reranked_hits=[RerankedSearchHit.model_validate(hit_data)],
        top_n=5,
    )

    assert pack.items == []


def test_citation_validation_accepts_known_ids():
    pack = build_evidence_pack_from_hybrid(
        requirement="Python 后端开发",
        hybrid_hits=[make_hybrid_hit(1, rank=1, fusion_score=0.03)],
        top_n=1,
        fallback_reason="test",
    )

    result = validate_evidence_citations(
        evidence_pack=pack,
        cited_chunk_ids=[1],
    )

    assert result.valid is True


def test_citation_validation_rejects_unknown_and_duplicate_ids():
    pack = build_evidence_pack_from_hybrid(
        requirement="Python 后端开发",
        hybrid_hits=[make_hybrid_hit(1, rank=1, fusion_score=0.03)],
        top_n=1,
        fallback_reason="test",
    )

    result = validate_evidence_citations(
        evidence_pack=pack,
        cited_chunk_ids=[1, 1, 999],
    )

    assert result.valid is False
    assert result.unknown_chunk_ids == [999]
    assert result.duplicate_chunk_ids == [1]


def test_report_citation_validation_deduplicates_shared_chunks():
    first_pack = build_evidence_pack_from_hybrid(
        requirement="Python 后端开发",
        hybrid_hits=[make_hybrid_hit(1, rank=1, fusion_score=0.03)],
        top_n=1,
        fallback_reason="test",
    )
    second_pack = EvidencePack(
        requirement="Redis 缓存",
        items=first_pack.items,
        rerank_applied=False,
    )

    result = validate_report_citations(
        result_json={"matches": [{"chunk_id": 1}]},
        evidence_packs=[first_pack, second_pack],
    )

    assert result.valid is True
    assert result.cited_chunk_ids == [1]


def test_citation_validation_rejects_missing_citation():
    pack = build_evidence_pack_from_hybrid(
        requirement="Python 后端开发",
        hybrid_hits=[make_hybrid_hit(1, rank=1, fusion_score=0.03)],
        top_n=1,
        fallback_reason="test",
    )

    result = validate_evidence_citations(
        evidence_pack=pack,
        cited_chunk_ids=[],
    )

    assert result.valid is False
    assert result.missing_citation is True
