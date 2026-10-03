# 提供简历文件上传和最小查询接口。

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResumeFileError
from app.core.response import success_response
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db_session
from app.dependencies.rate_limit import make_rate_limit_dependency
from app.repositories import ResumeRepository
from app.schemas.auth import CurrentUser
from app.schemas.resume_upload import (
    ResumeDetail,
    ResumeSummary,
    ResumeUploadResponse,
    ResumeVersionSummary,
)
from app.services.resume_file_parser import (
    MAX_RESUME_FILE_BYTES,
    parse_resume_file_async,
)
from app.services.resume_ingestion import persist_parsed_resume


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

    try:
        async with session.begin():
            result = await persist_parsed_resume(
                session,
                user_id=current_user.id,
                parsed=parsed,
                resume_id=resume_id,
                title=title,
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
        )
    )


@router.get("")
async def list_resumes_endpoint(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("resume_list")
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
        make_rate_limit_dependency("resume_read")
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


__all__ = ["router"]
