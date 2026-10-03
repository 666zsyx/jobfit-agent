# 验证向量索引过滤、删除和维度约束。

import pytest

from app.services.embeddings import FastEmbedEmbeddingProvider
from app.services.vector_index import (
    ChromaVectorIndex,
    VectorRecord,
)


def test_fastembed_provider_resolves_dimension():
    provider = FastEmbedEmbeddingProvider(
        model_name="BAAI/bge-small-zh-v1.5",
        cache_dir=".cache/fastembed",
    )

    assert provider.dimension == 512


def test_chroma_vector_index_filters_and_deletes(tmp_path):
    index = ChromaVectorIndex(
        path=str(tmp_path / "chroma"),
        collection_name="test_collection",
        model_name="fake-model",
        dimension=2,
    )
    index.upsert(
        [
            VectorRecord(
                chunk_id=1,
                vector=[1.0, 0.0],
                metadata={"user_id": 10, "resume_version_id": 1001},
            ),
            VectorRecord(
                chunk_id=2,
                vector=[0.0, 1.0],
                metadata={"user_id": 20, "resume_version_id": 2001},
            ),
        ]
    )

    results = index.query(
        user_id=10,
        resume_version_id=1001,
        query_vector=[1.0, 0.0],
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].chunk_id == 1
    assert results[0].similarity == pytest.approx(1.0)

    deleted = index.delete_resume_version(
        user_id=10,
        resume_version_id=1001,
    )
    assert deleted == 1

    after_delete = index.query(
        user_id=10,
        resume_version_id=1001,
        query_vector=[1.0, 0.0],
        top_k=5,
    )
    assert after_delete == []


def test_chroma_vector_index_rejects_wrong_dimension(tmp_path):
    index = ChromaVectorIndex(
        path=str(tmp_path / "chroma"),
        collection_name="test_collection",
        model_name="fake-model",
        dimension=2,
    )

    with pytest.raises(ValueError, match="向量维度不匹配"):
        index.upsert(
            [
                VectorRecord(
                    chunk_id=1,
                    vector=[1.0, 0.0, 0.0],
                    metadata={"user_id": 10, "resume_version_id": 1001},
                )
            ]
        )
