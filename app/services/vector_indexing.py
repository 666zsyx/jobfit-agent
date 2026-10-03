# 把 PostgreSQL Chunk 增量写入向量索引。

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import (
    KnowledgeChunkRepository,
    ResumeVersionRepository,
)
from app.schemas.knowledge import RESUME_CHUNKER_VERSION
from app.services.embeddings import EmbeddingProvider
from app.services.vector_index import VectorIndex, VectorRecord


def _validate_runtime(
    embedding_provider: EmbeddingProvider,
    vector_index: VectorIndex,
) -> None:
    if embedding_provider.model_name != vector_index.model_name:
        raise ValueError("EmbeddingProvider 与 VectorIndex 的模型不一致")

    if embedding_provider.dimension != vector_index.dimension:
        raise ValueError("EmbeddingProvider 与 VectorIndex 的维度不一致")


async def index_resume_version_chunks(
    session: AsyncSession,
    *,
    user_id: int,
    resume_version_id: int,
    embedding_provider: EmbeddingProvider,
    vector_index: VectorIndex,
) -> list[int]:
    """为简历版本的全部当前 Chunk 建立向量。"""

    _validate_runtime(embedding_provider, vector_index)

    version_repository = ResumeVersionRepository(session)
    resume_version = await version_repository.get_for_user(
        resume_version_id=resume_version_id,
        user_id=user_id,
    )

    if resume_version is None:
        raise LookupError("简历版本不存在或无权访问")

    chunk_repository = KnowledgeChunkRepository(session)
    chunks = await chunk_repository.list_for_resume_version(
        user_id=user_id,
        resume_version_id=resume_version_id,
        chunker_version=RESUME_CHUNKER_VERSION,
    )
    chunks = [
        chunk
        for chunk in chunks
        if chunk.index_status != "stale"
    ]

    if not chunks:
        raise ValueError("简历版本没有可索引的 Chunk")

    texts = [
        f"{chunk.title}\n{chunk.content}"
        for chunk in chunks
    ]
    chunk_ids = [chunk.chunk_id for chunk in chunks]

    try:
        vectors = await asyncio.to_thread(
            embedding_provider.embed_documents,
            texts,
        )
        records = [
            VectorRecord(
                chunk_id=chunk.chunk_id,
                vector=vector,
                metadata={
                    "chunk_id": chunk.chunk_id,
                    "user_id": user_id,
                    "resume_version_id": resume_version_id,
                    "chunker_version": chunk.chunker_version,
                    "section_type": chunk.section_type,
                    "content_hash": chunk.content_hash,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        await asyncio.to_thread(vector_index.upsert, records)
    except Exception:
        await chunk_repository.mark_many_index_status_for_user(
            chunk_ids=chunk_ids,
            user_id=user_id,
            index_status="failed",
        )
        raise

    await chunk_repository.mark_many_index_status_for_user(
        chunk_ids=chunk_ids,
        user_id=user_id,
        index_status="indexed",
        embedding_model=embedding_provider.model_name,
        embedding_dimension=embedding_provider.dimension,
    )
    return chunk_ids


async def rebuild_resume_version_index(
    session: AsyncSession,
    *,
    user_id: int,
    resume_version_id: int,
    embedding_provider: EmbeddingProvider,
    vector_index: VectorIndex,
) -> list[int]:
    """删除旧向量后从 PostgreSQL Chunk 完整重建。"""

    await asyncio.to_thread(
        vector_index.delete_resume_version,
        user_id=user_id,
        resume_version_id=resume_version_id,
    )
    return await index_resume_version_chunks(
        session,
        user_id=user_id,
        resume_version_id=resume_version_id,
        embedding_provider=embedding_provider,
        vector_index=vector_index,
    )
