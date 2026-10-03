# 把解析后的简历保存为 Resume 和 ResumeVersion。

from __future__ import annotations

import logging
from pathlib import PurePath
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cost_tracking import (
    finish_usage_collection,
    start_usage_collection,
)
from app.core.exceptions import (
    LLMServiceError,
    StructuredOutputError,
    UnsafeInputError,
)
from app.repositories import ResumeRepository, ResumeVersionRepository
from app.services.resume_extraction import extract_resume_sections
from app.services.resume_file_parser import ResumeParseResult


logger = logging.getLogger(__name__)


class ResumeExtractionOutcome(BaseModel):
    status: Literal["completed", "failed", "skipped"]
    extracted_sections: dict | None = None
    error_code: str | None = None
    total_tokens: int = Field(default=0, ge=0)


class ResumeIngestionResult(BaseModel):
    resume_id: int = Field(gt=0)
    resume_version_id: int = Field(gt=0)
    version_no: int = Field(gt=0)
    title: str
    source_type: str
    char_count: int = Field(ge=1)


async def extract_resume_sections_safely(
    resume_text: str,
) -> ResumeExtractionOutcome:
    """可选执行结构提取，失败不影响 raw_text 保存。"""

    usage_token = start_usage_collection()
    try:
        extraction = await extract_resume_sections(resume_text)
    except StructuredOutputError:
        records = finish_usage_collection(usage_token)
        return ResumeExtractionOutcome(
            status="failed",
            error_code="structured_output_error",
            total_tokens=sum(record.total_tokens for record in records),
        )
    except LLMServiceError:
        records = finish_usage_collection(usage_token)
        return ResumeExtractionOutcome(
            status="failed",
            error_code="llm_service_error",
            total_tokens=sum(record.total_tokens for record in records),
        )
    except UnsafeInputError:
        records = finish_usage_collection(usage_token)
        return ResumeExtractionOutcome(
            status="failed",
            error_code="unsafe_input",
            total_tokens=sum(record.total_tokens for record in records),
        )
    except Exception:
        records = finish_usage_collection(usage_token)
        logger.warning("简历结构提取失败", exc_info=True)
        return ResumeExtractionOutcome(
            status="failed",
            error_code="extraction_failed",
            total_tokens=sum(record.total_tokens for record in records),
        )

    records = finish_usage_collection(usage_token)
    return ResumeExtractionOutcome(
        status="completed",
        extracted_sections=extraction.model_dump(mode="json"),
        total_tokens=sum(record.total_tokens for record in records),
    )


def _default_resume_title(parsed: ResumeParseResult) -> str:
    stem = PurePath(parsed.original_filename).stem.strip()
    return (stem or "上传简历")[:100]


async def persist_parsed_resume(
    session: AsyncSession,
    *,
    user_id: int,
    parsed: ResumeParseResult,
    resume_id: int | None = None,
    title: str | None = None,
    extracted_sections: dict | None = None,
) -> ResumeIngestionResult:
    """创建新简历或给已有简历追加新版本，不提交事务。"""

    resume_repository = ResumeRepository(session)
    version_repository = ResumeVersionRepository(session)
    resolved_title = (title or "").strip() or _default_resume_title(parsed)

    if resume_id is None:
        resume = await resume_repository.create(
            user_id=user_id,
            title=resolved_title,
        )
        version = await version_repository.create_for_user(
            resume_id=resume.resume_id,
            user_id=user_id,
            version_no=1,
            raw_text=parsed.text,
            extracted_sections=extracted_sections,
            source_type=parsed.source_type,
        )
        resolved_title = resume.title
    else:
        version = await version_repository.create_next_for_user(
            resume_id=resume_id,
            user_id=user_id,
            raw_text=parsed.text,
            extracted_sections=extracted_sections,
            source_type=parsed.source_type,
        )
        resume = await resume_repository.get_for_user(
            resume_id,
            user_id,
        )
        if resume is None:
            raise LookupError("简历不存在或无权访问")
        resolved_title = resume.title

    return ResumeIngestionResult(
        resume_id=resume.resume_id,
        resume_version_id=version.resume_version_id,
        version_no=version.version_no,
        title=resolved_title,
        source_type=version.source_type,
        char_count=len(version.raw_text),
    )


__all__ = [
    "ResumeExtractionOutcome",
    "ResumeIngestionResult",
    "extract_resume_sections_safely",
    "persist_parsed_resume",
]
