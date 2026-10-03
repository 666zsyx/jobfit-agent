# 实现简历 section-aware chunking 和幂等摄入。

import hashlib
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeChunk
from app.repositories import (
    KnowledgeChunkRepository,
    ResumeVersionRepository,
)
from app.schemas.knowledge import (
    RESUME_CHUNKER_VERSION,
    KnowledgeChunkDraft,
)
from app.schemas.resume import ResumeExtraction, ResumeSection


DEFAULT_MAX_CHUNK_CHARS = 600
DEFAULT_CHUNK_OVERLAP_CHARS = 80
SEMANTIC_BOUNDARY_CHARS = frozenset("。！？!?；;\n")


@dataclass(frozen=True)
class _TextSpan:
    start: int
    end: int


def _split_semantic_spans(content: str) -> list[_TextSpan]:
    """按句末和换行切出语义片段，并保留原始偏移。"""

    spans: list[_TextSpan] = []
    start = 0

    for index, char in enumerate(content):
        if char not in SEMANTIC_BOUNDARY_CHARS:
            continue

        end = index + 1
        if content[start:end].strip():
            spans.append(_TextSpan(start=start, end=end))

        start = end

    if start < len(content) and content[start:].strip():
        spans.append(_TextSpan(start=start, end=len(content)))

    return spans


def _append_span(
    spans: list[_TextSpan],
    current_start: int | None,
    current_end: int | None,
) -> None:
    if current_start is None or current_end is None:
        return

    spans.append(_TextSpan(start=current_start, end=current_end))


def _chunk_content_spans(
    content: str,
    *,
    max_chars: int,
    overlap_chars: int,
) -> list[_TextSpan]:
    """把语义片段打包成带重叠的 Chunk 偏移。"""

    semantic_spans = _split_semantic_spans(content)

    if not semantic_spans:
        raise ValueError("section content 不能为空")

    chunk_spans: list[_TextSpan] = []
    current_start: int | None = None
    current_end: int | None = None

    for span in semantic_spans:
        span_length = span.end - span.start

        if span_length > max_chars:
            _append_span(chunk_spans, current_start, current_end)
            current_start = None
            current_end = None

            cursor = span.start

            while cursor < span.end:
                end = min(cursor + max_chars, span.end)
                chunk_spans.append(_TextSpan(start=cursor, end=end))

                if end == span.end:
                    break

                cursor = end - overlap_chars

            continue

        if current_start is None or current_end is None:
            current_start = span.start
            current_end = span.end
            continue

        if span.end - current_start > max_chars:
            _append_span(chunk_spans, current_start, current_end)

            allowed_overlap = max_chars - span_length
            actual_overlap = min(overlap_chars, allowed_overlap)
            current_start = current_end - actual_overlap
            current_end = span.end
            continue

        current_end = span.end

    _append_span(chunk_spans, current_start, current_end)
    return chunk_spans


def chunk_resume_sections(
    sections: list[ResumeSection],
    *,
    max_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> list[KnowledgeChunkDraft]:
    """把简历 section 确定性切分为待持久化 Chunk。"""

    if not sections:
        raise ValueError("sections 不能为空")

    if max_chars < 1:
        raise ValueError("max_chars 必须大于等于 1")

    if overlap_chars < 0:
        raise ValueError("overlap_chars 不能小于 0")

    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars 必须小于 max_chars")

    drafts: list[KnowledgeChunkDraft] = []
    position = 1

    for section in sections:
        spans = _chunk_content_spans(
            section.content,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )

        for span in spans:
            content = section.content[span.start:span.end]
            content_hash = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()

            drafts.append(
                KnowledgeChunkDraft(
                    section_type=section.section_type,
                    title=section.title,
                    content=content,
                    content_hash=content_hash,
                    position=position,
                    start_offset=span.start,
                    end_offset=span.end,
                    chunker_version=RESUME_CHUNKER_VERSION,
                )
            )
            position += 1

    return drafts


async def ingest_resume_version_chunks(
    session: AsyncSession,
    *,
    user_id: int,
    resume_version_id: int,
) -> list[KnowledgeChunk]:
    """读取简历版本、切分 Chunk 并幂等写入 PostgreSQL。"""

    version_repository = ResumeVersionRepository(session)
    resume_version = await version_repository.get_for_user(
        resume_version_id=resume_version_id,
        user_id=user_id,
        for_update=True,
    )

    if resume_version is None:
        raise LookupError("简历版本不存在或无权访问")

    if resume_version.extracted_sections is None:
        raise ValueError("简历版本没有结构化分段，无法建立 Chunk")

    extraction = ResumeExtraction.model_validate(
        resume_version.extracted_sections
    )
    drafts = chunk_resume_sections(extraction.sections)

    if not drafts:
        raise ValueError("没有生成任何 Chunk")

    chunk_repository = KnowledgeChunkRepository(session)
    chunks: list[KnowledgeChunk] = []
    active_positions: set[int] = set()

    for draft in drafts:
        chunk = await chunk_repository.upsert_for_user(
            user_id=user_id,
            resume_version_id=resume_version_id,
            section_type=draft.section_type,
            title=draft.title,
            content=draft.content,
            content_hash=draft.content_hash,
            position=draft.position,
            start_offset=draft.start_offset,
            end_offset=draft.end_offset,
            chunker_version=draft.chunker_version,
        )
        chunks.append(chunk)
        active_positions.add(draft.position)

    await chunk_repository.mark_stale_except_positions(
        user_id=user_id,
        resume_version_id=resume_version_id,
        chunker_version=RESUME_CHUNKER_VERSION,
        active_positions=active_positions,
    )

    return chunks
