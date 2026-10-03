# 使用向量索引召回 Chunk，并回 PostgreSQL 读取权威原文。

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import KnowledgeChunkRepository
from app.schemas.knowledge import RESUME_CHUNKER_VERSION, VectorSearchHit
from app.services.embeddings import EmbeddingProvider
from app.services.vector_index import VectorIndex
from app.services.vector_indexing import _validate_runtime


async def search_resume_chunks_by_vector(
    session: AsyncSession,
    *,
    user_id: int,
    resume_version_id: int,
    requirement: str,
    top_k: int,
    embedding_provider: EmbeddingProvider,
    vector_index: VectorIndex,
) -> list[VectorSearchHit]:
    """按单条岗位要求执行纯向量召回。"""

    _validate_runtime(embedding_provider, vector_index)

    if not requirement.strip():
        raise ValueError("requirement 不能为空")

    if top_k < 1:
        raise ValueError("top_k 必须大于等于 1")

    query_vector = await asyncio.to_thread(
        embedding_provider.embed_query,
        requirement,
    )
    vector_hits = await asyncio.to_thread(
        vector_index.query,
        user_id=user_id,
        resume_version_id=resume_version_id,
        query_vector=query_vector,
        top_k=top_k,
    )

    if not vector_hits:
        return []

    chunk_ids = [hit.chunk_id for hit in vector_hits]
    chunk_repository = KnowledgeChunkRepository(session)
    chunks = await chunk_repository.get_many_for_user(
        chunk_ids=chunk_ids,
        user_id=user_id,
    )
    chunks_by_id = {
        chunk.chunk_id: chunk
        for chunk in chunks
        if chunk.resume_version_id == resume_version_id
        and chunk.chunker_version == RESUME_CHUNKER_VERSION
        and chunk.index_status == "indexed"
    }

    results: list[VectorSearchHit] = []

    for vector_hit in vector_hits:
        chunk = chunks_by_id.get(vector_hit.chunk_id)

        if chunk is None:
            continue

        results.append(
            VectorSearchHit(
                chunk_id=chunk.chunk_id,
                user_id=chunk.user_id,
                resume_version_id=chunk.resume_version_id,
                section_type=chunk.section_type,
                title=chunk.title,
                content=chunk.content,
                content_hash=chunk.content_hash,
                position=chunk.position,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                chunker_version=chunk.chunker_version,
                similarity=vector_hit.similarity,
                rank=len(results) + 1,
            )
        )

    return results
