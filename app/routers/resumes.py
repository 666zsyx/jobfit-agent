# 提供简历文件上传和最小查询接口。

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.client import get_redis_client
from app.core.exceptions import ResumeFileError
from app.core.response import success_response
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db_session
from app.dependencies.rate_limit import make_rate_limit_dependency
from app.repositories import ResumeRepository, ResumeVersionRepository
from app.schemas.auth import CurrentUser
from app.schemas.resume_upload import (
    ResumeDetail,
    ResumeExtractionResponse,
    ResumeSummary,
    ResumeUploadResponse,
    ResumeVersionSummary,
)
from app.services.resume_file_parser import (
    MAX_RESUME_FILE_BYTES,
    parse_resume_file_async,
)
from app.services.rate_limit import record_daily_token_usage
from app.services.resume_ingestion import (
    ResumeExtractionOutcome,
    extract_resume_sections_safely,
    persist_parsed_resume,
)


router = APIRouter(prefix="/api/resumes", tags=["resumes"])


def _preview(text: str, limit: int = 200) -> str:
    compact = " ".join(text.split())
    return compact[:limit]


def _version_summary(version) -> ResumeVersionSummary:
    return ResumeVersionSummary(
        resume_version_id=version.resume_version_id,
        version_no=version.version_no,
        source_type=version.source_type,
        char_count=len(version.raw_text),
        preview=_preview(version.raw_text),
        has_extracted_sections=bool(version.extracted_sections),
        created_at=version.created_at,
    )


def _resume_summary(resume) -> ResumeSummary:
    latest = resume.versions[-1] if resume.versions else None
    return ResumeSummary(
        resume_id=resume.resume_id,
        title=resume.title,
        status=resume.status,
        latest_version_no=latest.version_no if latest else 0,
        latest_source_type=latest.source_type if latest else None,
        latest_char_count=len(latest.raw_text) if latest else 0,
        created_at=resume.created_at,
        updated_at=resume.updated_at,
    )


async def _read_upload_limited(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_RESUME_FILE_BYTES:
                raise ResumeFileError(
                    message="文件超过 10 MB 限制",
                    error_code="file_too_large",
                    status_code=413,
                )
            chunks.append(chunk)
    finally:
        await file.close()
    return b"".join(chunks)


@router.post("/upload")
async def upload_resume_endpoint(
    file: UploadFile = File(...),
    resume_id: int | None = Form(default=None),
    title: str | None = Form(default=None),
    extract_sections: bool = Form(default=True),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("resume_upload")
    ),
) -> dict:
    """上传并解析简历文件，保存为新的简历版本。"""

    data = await _read_upload_limited(file)
    parsed = await parse_resume_file_async(
        filename=file.filename,
        content_type=file.content_type,
        data=data,
    )

    if extract_sections:
        extraction = await extract_resume_sections_safely(parsed.text)
    else:
        extraction = ResumeExtractionOutcome(status="skipped")
    await record_daily_token_usage(
        get_redis_client(),
        user_id=current_user.id,
        total_tokens=extraction.total_tokens,
    )

    try:
        async with session.begin():
            result = await persist_parsed_resume(
                session,
                user_id=current_user.id,
                parsed=parsed,
                resume_id=resume_id,
                title=title,
                extracted_sections=extraction.extracted_sections,
            )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return success_response(
        data=ResumeUploadResponse(
            resume_id=result.resume_id,
            resume_version_id=result.resume_version_id,
            version_no=result.version_no,
            title=result.title,
            source_type=result.source_type,
            char_count=result.char_count,
            preview=_preview(parsed.text),
            extraction_status=extraction.status,
            extraction_error_code=extraction.error_code,
        )
    )


@router.get("")
async def list_resumes_endpoint(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency(
            "resume_list",
            enforce_token_quota=False,
        )
    ),
) -> dict:
    """查询当前用户的简历列表。"""

    resumes = await ResumeRepository(session).list_for_user(
        current_user.id,
        with_versions=True,
    )
    return success_response(
        data=[_resume_summary(resume) for resume in resumes]
    )


@router.get("/{resume_id}")
async def get_resume_endpoint(
    resume_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency(
            "resume_read",
            enforce_token_quota=False,
        )
    ),
) -> dict:
    """查询当前用户的一份简历及版本。"""

    resume = await ResumeRepository(session).get_for_user(
        resume_id=resume_id,
        user_id=current_user.id,
        with_versions=True,
    )
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="简历不存在或无权访问",
        )

    return success_response(
        data=ResumeDetail(
            resume_id=resume.resume_id,
            title=resume.title,
            status=resume.status,
            created_at=resume.created_at,
            updated_at=resume.updated_at,
            versions=[
                _version_summary(version)
                for version in resume.versions
            ],
        )
    )


@router.post("/{resume_id}/versions/{resume_version_id}/extract")
async def extract_resume_version_endpoint(
    resume_id: int,
    resume_version_id: int,
    force: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("resume_extract")
    ),
) -> dict:
    """重试或强制执行简历结构化提取。"""

    async with session.begin():
        version = await ResumeVersionRepository(session).get_for_user(
            resume_version_id=resume_version_id,
            user_id=current_user.id,
            for_update=True,
        )
        if version is None or version.resume_id != resume_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="简历版本不存在或无权访问",
            )

        if version.extracted_sections and not force:
            extraction = ResumeExtractionOutcome(
                status="completed",
                extracted_sections=version.extracted_sections,
            )
        else:
            extraction = await extract_resume_sections_safely(
                version.raw_text
            )
            if extraction.status == "completed":
                version.extracted_sections = extraction.extracted_sections
                await session.flush()

    await record_daily_token_usage(
        get_redis_client(),
        user_id=current_user.id,
        total_tokens=extraction.total_tokens,
    )
    return success_response(
        data=ResumeExtractionResponse(
            resume_id=resume_id,
            resume_version_id=resume_version_id,
            extraction_status=extraction.status,
            extraction_error_code=extraction.error_code,
            has_extracted_sections=bool(version.extracted_sections),
        )
    )


__all__ = ["router"]
