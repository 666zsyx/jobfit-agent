# 创建进程级复用的 Embedding、Reranker 和向量索引实例。

from threading import RLock

from app.core.config import settings
from app.services.embeddings import (
    EmbeddingProvider,
    FastEmbedEmbeddingProvider,
)
from app.services.reranking import FastEmbedReranker, Reranker
from app.services.vector_index import ChromaVectorIndex, VectorIndex


_embedding_provider: EmbeddingProvider | None = None
_vector_index: VectorIndex | None = None
_reranker: Reranker | None = None
_runtime_lock = RLock()


def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider

    if _embedding_provider is not None:
        return _embedding_provider

    with _runtime_lock:
        if _embedding_provider is None:
            _embedding_provider = FastEmbedEmbeddingProvider(
                model_name=settings.embedding_model_name,
                cache_dir=settings.embedding_cache_path,
            )

    return _embedding_provider


def get_vector_index() -> VectorIndex:
    global _vector_index

    if _vector_index is not None:
        return _vector_index

    with _runtime_lock:
        if _vector_index is None:
            provider = get_embedding_provider()
            _vector_index = ChromaVectorIndex(
                path=settings.vector_index_path,
                collection_name=settings.vector_collection_name,
                model_name=provider.model_name,
                dimension=provider.dimension,
            )

    return _vector_index


def get_reranker() -> Reranker:
    global _reranker

    if _reranker is not None:
        return _reranker

    with _runtime_lock:
        if _reranker is None:
            _reranker = FastEmbedReranker(
                model_name=settings.reranker_model_name,
                cache_dir=settings.embedding_cache_path,
            )

    return _reranker


def reset_rag_runtime() -> None:
    """清空进程级实例，测试和生命周期重置时使用。"""

    global _embedding_provider
    global _vector_index
    global _reranker

    with _runtime_lock:
        _embedding_provider = None
        _vector_index = None
        _reranker = None
