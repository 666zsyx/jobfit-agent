# 验证 BM25 token 和 RRF 融合排序。

import pytest

from app.schemas.knowledge import (
    HybridSearchHit,
    LexicalSearchHit,
    VectorSearchHit,
)
from app.services.hybrid_search import fuse_retrieval_hits
from app.services.keyword_search import tokenize


def make_common(
    chunk_id: int,
    *,
    content_hash: str | None = None,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "user_id": 10,
        "resume_version_id": 1001,
        "section_type": "project_experience",
        "title": f"项目 {chunk_id}",
        "content": f"项目内容 {chunk_id}",
        "content_hash": content_hash or str(chunk_id) * 64,
        "position": chunk_id,
        "start_offset": 0,
        "end_offset": 10,
        "chunker_version": "v1",
    }


def make_keyword_hit(
    chunk_id: int,
    rank: int,
    score: float,
) -> LexicalSearchHit:
    return LexicalSearchHit(
        **make_common(chunk_id),
        bm25_score=score,
        rank=rank,
    )


def make_vector_hit(
    chunk_id: int,
    rank: int,
    similarity: float,
) -> VectorSearchHit:
    return VectorSearchHit(
        **make_common(chunk_id),
        similarity=similarity,
        rank=rank,
    )


def test_tokenize_keeps_technical_terms_and_drops_common_word():
    tokens = tokenize("熟悉 Python 和 FastAPI")

    assert "python" in tokens
    assert "fastapi" in tokens
    assert "和" not in tokens


def test_rrf_rewards_chunk_found_by_both_retrievers():
    results = fuse_retrieval_hits(
        keyword_hits=[
            make_keyword_hit(1, 1, 10.0),
            make_keyword_hit(2, 2, 8.0),
        ],
        vector_hits=[
            make_vector_hit(2, 1, 0.91),
            make_vector_hit(3, 2, 0.88),
        ],
        top_n=3,
    )

    assert [result.chunk_id for result in results] == [2, 1, 3]
    assert results[0].lexical_rank == 2
    assert results[0].vector_rank == 1


def test_fusion_deduplicates_same_chunk():
    results = fuse_retrieval_hits(
        keyword_hits=[make_keyword_hit(1, 1, 10.0)],
        vector_hits=[make_vector_hit(1, 1, 0.9)],
        top_n=10,
    )

    assert len(results) == 1
    assert results[0].chunk_id == 1
    assert results[0].fusion_score == pytest.approx(2 / 61)


def test_fusion_supports_single_retriever():
    results = fuse_retrieval_hits(
        keyword_hits=[make_keyword_hit(1, 1, 10.0)],
        vector_hits=[],
        top_n=10,
    )

    assert isinstance(results[0], HybridSearchHit)
    assert results[0].chunk_id == 1
    assert results[0].vector_rank is None


def test_fusion_rejects_mismatched_content_hash():
    keyword_hit = make_keyword_hit(1, 1, 10.0)
    vector_hit = make_vector_hit(1, 1, 0.9).model_copy(
        update={"content_hash": "a" * 64}
    )

    with pytest.raises(ValueError, match="内容哈希不一致"):
        fuse_retrieval_hits(
            keyword_hits=[keyword_hit],
            vector_hits=[vector_hit],
            top_n=10,
        )


def test_fusion_rejects_zero_weights():
    with pytest.raises(ValueError, match="至少一个召回权重"):
        fuse_retrieval_hits(
            keyword_hits=[],
            vector_hits=[],
            keyword_weight=0,
            vector_weight=0,
            top_n=10,
        )
