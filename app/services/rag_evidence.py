# 把 RAG 检索转换成 JobFit 工具可消费的证据结果。

import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import ResumeVersionRepository
from app.schemas.evidence import (
    EvidenceItem,
    EvidenceSearchResult,
    RequirementEvidence,
)
from app.schemas.knowledge import (
    EvidenceItem as KnowledgeEvidenceItem,
)
from app.schemas.knowledge import (
    EvidencePack,
)
from app.services.chunking import ingest_resume_version_chunks
from app.services.evidence_pipeline import (
    search_resume_chunks_with_evidence,
)
from app.services.query_variants import build_query_variants
from app.services.rag_runtime import (
    get_embedding_provider,
    get_reranker,
    get_vector_index,
)
from app.services.resume_extraction import extract_resume_sections
from app.services.vector_indexing import index_resume_version_chunks

DEFAULT_RAG_CANDIDATE_TOP_K = 10
DEFAULT_RAG_RERANK_TOP_N = 5
DEFAULT_RAG_EVIDENCE_TOP_N = 3


def _normalize_rerank_score(score: float) -> float:
    bounded_score = max(-60.0, min(60.0, score))
    return 1.0 / (1.0 + math.exp(-bounded_score))


def _evidence_item_from_pack(
    pack: EvidencePack,
    evidence,
) -> EvidenceItem:
    normalized_score = (
        _normalize_rerank_score(evidence.relevance_score)
        if pack.rerank_applied
        else 0.5
    )

    return EvidenceItem(
        chunk_id=evidence.chunk_id,
        source_version_id=evidence.resume_version_id,
        position=evidence.position,
        section_type=evidence.section_type,
        title=evidence.title,
        content=evidence.content,
        score=round(normalized_score, 6),
        rerank_score=(
            evidence.relevance_score
            if pack.rerank_applied
            else None
        ),
    )


async def prepare_resume_rag(
    session: AsyncSession,
    *,
    user_id: int,
    resume_version_id: int,
) -> None:
    """确保简历版本已有分段、Chunk 和向量索引。"""

    version_repository = ResumeVersionRepository(session)
    resume_version = await version_repository.get_for_user(
        resume_version_id=resume_version_id,
        user_id=user_id,
        for_update=True,
    )

    if resume_version is None:
        raise LookupError("简历版本不存在或无权访问")

    extracted_sections = resume_version.extracted_sections
    if (
        not isinstance(extracted_sections, dict)
        or not extracted_sections.get("sections")
    ):
        extraction = await extract_resume_sections(
            resume_version.raw_text
        )
        resume_version.extracted_sections = extraction.model_dump(
            mode="json"
        )
        await session.flush()

    await ingest_resume_version_chunks(
        session,
        user_id=user_id,
        resume_version_id=resume_version_id,
    )
    await index_resume_version_chunks(
        session,
        user_id=user_id,
        resume_version_id=resume_version_id,
        embedding_provider=get_embedding_provider(),
        vector_index=get_vector_index(),
    )


def _merge_variant_packs(
    requirement: str,
    packs: list[EvidencePack],
) -> EvidencePack:
    if len(packs) == 1:
        return packs[0].model_copy(
            update={"requirement": requirement}
        )

    items_by_chunk: dict[int, KnowledgeEvidenceItem] = {}
    for pack in packs:
        for item in pack.items:
            existing = items_by_chunk.get(item.chunk_id)
            if (
                existing is None
                or item.relevance_score > existing.relevance_score
            ):
                items_by_chunk[item.chunk_id] = item

    items = sorted(
        items_by_chunk.values(),
        key=lambda item: item.relevance_score,
        reverse=True,
    )[:DEFAULT_RAG_EVIDENCE_TOP_N]

    fallback_reason = next(
        (
            pack.fallback_reason
            for pack in packs
            if pack.fallback_reason
        ),
        None,
    )
    return EvidencePack(
        requirement=requirement,
        items=items,
        rerank_applied=any(pack.rerank_applied for pack in packs),
        degraded=any(pack.degraded for pack in packs),
        fallback_reason=fallback_reason,
    )


async def search_requirements_with_rag(
    session: AsyncSession,
    *,
    user_id: int,
    resume_version_id: int,
    requirements: list[str],
) -> tuple[EvidenceSearchResult, list[EvidencePack]]:
    """对每条岗位要求执行混合检索、Rerank 和证据整理。"""

    embedding_provider = get_embedding_provider()
    vector_index = get_vector_index()
    reranker = get_reranker()

    matches: list[RequirementEvidence] = []
    evidence_packs: list[EvidencePack] = []

    for requirement in requirements:
        variant_packs = []
        for query in build_query_variants(requirement):
            variant_pack = await search_resume_chunks_with_evidence(
                session,
                user_id=user_id,
                resume_version_id=resume_version_id,
                requirement=query,
                candidate_top_k=DEFAULT_RAG_CANDIDATE_TOP_K,
                rerank_candidate_top_n=DEFAULT_RAG_RERANK_TOP_N,
                evidence_top_n=DEFAULT_RAG_EVIDENCE_TOP_N,
                embedding_provider=embedding_provider,
                vector_index=vector_index,
                reranker=reranker,
            )
            variant_packs.append(variant_pack)
        pack = _merge_variant_packs(requirement, variant_packs)
        evidence_packs.append(pack)
        matches.append(
            RequirementEvidence(
                requirement=requirement,
                evidence=[
                    _evidence_item_from_pack(pack, item)
                    for item in pack.items
                ],
            )
        )

    return (
        EvidenceSearchResult(
            requirements=requirements,
            matches=matches,
        ),
        evidence_packs,
    )
