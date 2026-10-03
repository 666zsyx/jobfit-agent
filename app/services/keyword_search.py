# 实现基于词项和 BM25 的简历 Chunk 关键词召回。

import math
import re
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import KnowledgeChunkRepository
from app.schemas.knowledge import (
    RESUME_CHUNKER_VERSION,
    LexicalSearchHit,
)


ENGLISH_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_+#.\-]*")
CHINESE_RUN_PATTERN = re.compile(r"[\u4e00-\u9fff]+")
STOP_TOKENS = frozenset(
    {"的", "了", "和", "与", "或", "有", "在", "是", "为"}
)
BM25_K1 = 1.5
BM25_B = 0.75


def tokenize(text: str) -> list[str]:
    """生成适用于中英技术文本的检索 token。"""

    normalized = text.lower()
    tokens = ENGLISH_TOKEN_PATTERN.findall(normalized)

    for run in CHINESE_RUN_PATTERN.findall(normalized):
        if len(run) < 2:
            continue

        tokens.append(run)

        for index in range(len(run) - 1):
            tokens.append(run[index:index + 2])

    return [
        token
        for token in tokens
        if token not in STOP_TOKENS
    ]


def _document_frequencies(
    document_tokens: list[list[str]],
    query_tokens: set[str],
) -> dict[str, int]:
    frequencies = {token: 0 for token in query_tokens}

    for tokens in document_tokens:
        unique_tokens = set(tokens)

        for token in query_tokens:
            if token in unique_tokens:
                frequencies[token] += 1

    return frequencies


def _score_document(
    *,
    query_tokens: set[str],
    document_tokens: list[str],
    document_frequencies: dict[str, int],
    document_count: int,
    average_length: float,
) -> float:
    if not query_tokens or not document_tokens:
        return 0.0

    term_frequencies = Counter(document_tokens)
    document_length = len(document_tokens)
    score = 0.0

    for token in query_tokens:
        term_frequency = term_frequencies.get(token, 0)

        if term_frequency == 0:
            continue

        document_frequency = document_frequencies[token]
        inverse_document_frequency = math.log(
            1.0
            + (
                document_count - document_frequency + 0.5
            )
            / (document_frequency + 0.5)
        )
        length_normalization = (
            1.0
            - BM25_B
            + BM25_B * document_length / average_length
        )
        term_score = (
            inverse_document_frequency
            * term_frequency
            * (BM25_K1 + 1.0)
            / (term_frequency + BM25_K1 * length_normalization)
        )
        score += term_score

    return score


async def search_resume_chunks_by_keyword(
    session: AsyncSession,
    *,
    user_id: int,
    resume_version_id: int,
    requirement: str,
    top_k: int,
    chunker_version: str = RESUME_CHUNKER_VERSION,
) -> list[LexicalSearchHit]:
    """对当前简历版本的 Chunk 执行 BM25 关键词召回。"""

    normalized_requirement = requirement.strip()

    if not normalized_requirement:
        raise ValueError("requirement 不能为空")

    if top_k < 1:
        raise ValueError("top_k 必须大于等于 1")

    query_tokens = set(tokenize(normalized_requirement))

    if not query_tokens:
        return []

    chunk_repository = KnowledgeChunkRepository(session)
    chunks = await chunk_repository.list_for_resume_version(
        user_id=user_id,
        resume_version_id=resume_version_id,
        chunker_version=chunker_version,
    )
    chunks = [
        chunk
        for chunk in chunks
        if chunk.index_status != "stale"
    ]

    if not chunks:
        return []

    document_tokens = [
        tokenize(chunk.title) * 2 + tokenize(chunk.content)
        for chunk in chunks
    ]
    document_count = len(document_tokens)
    average_length = sum(
        len(tokens)
        for tokens in document_tokens
    ) / document_count
    document_frequencies = _document_frequencies(
        document_tokens,
        query_tokens,
    )

    scored_chunks = []

    for chunk, tokens in zip(chunks, document_tokens, strict=True):
        score = _score_document(
            query_tokens=query_tokens,
            document_tokens=tokens,
            document_frequencies=document_frequencies,
            document_count=document_count,
            average_length=average_length,
        )

        if score > 0:
            scored_chunks.append((chunk, score))

    scored_chunks.sort(
        key=lambda item: (
            -item[1],
            item[0].position,
            item[0].chunk_id,
        )
    )

    return [
        LexicalSearchHit(
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
            bm25_score=round(score, 6),
            rank=rank,
        )
        for rank, (chunk, score) in enumerate(
            scored_chunks[:top_k],
            start=1,
        )
    ]
