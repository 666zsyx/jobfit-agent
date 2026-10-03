# 把解析后的简历保存为 Resume 和 ResumeVersion。

from __future__ import annotations

from pathlib import PurePath

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import ResumeRepository, ResumeVersionRepository
from app.services.resume_file_parser import ResumeParseResult


class ResumeIngestionResult(BaseModel):
    resume_id: int = Field(gt=0)
    resume_version_id: int = Field(gt=0)
    version_no: int = Field(gt=0)
    title: str
    source_type: str
    char_count: int = Field(ge=1)


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
    "ResumeIngestionResult",
    "persist_parsed_resume",
]
