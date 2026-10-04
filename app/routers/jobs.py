# 提供岗位 JD 持久化和结构化提取接口。

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.client import get_redis_client
from app.core.cost_tracking import (
    finish_usage_collection,
    start_usage_collection,
)
from app.core.response import success_response
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db_session
from app.dependencies.rate_limit import make_rate_limit_dependency
from app.repositories import JobRepository
from app.schemas.auth import CurrentUser
from app.schemas.extraction import JobExtractionRequest
from app.schemas.job import (
    JobCreateRequest,
    JobDeleteResponse,
    JobDetail,
    JobSummary,
    JobUpdateRequest,
)
from app.services.extraction import extract_job
from app.services.rate_limit import record_daily_token_usage


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _preview(text: str, limit: int = 200) -> str:
    compact = " ".join(text.split())
    return compact[:limit]


def _job_summary(job) -> JobSummary:
    return JobSummary(
        job_id=job.job_id,
        title=job.title,
        company_name=job.company_name,
        status=job.status,
        job_description_preview=_preview(job.raw_description),
        has_extracted_requirements=bool(job.extracted_requirements),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _job_detail(job) -> JobDetail:
    return JobDetail(
        job_id=job.job_id,
        title=job.title,
        company_name=job.company_name,
        status=job.status,
        job_description=job.raw_description,
        job_description_preview=_preview(job.raw_description),
        extracted_requirements=job.extracted_requirements,
        has_extracted_requirements=bool(job.extracted_requirements),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_job_endpoint(
    request: JobCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("jobs_create")
    ),
) -> JSONResponse:
    """创建当前用户的岗位记录。"""

    requirements = (
        request.extracted_requirements.model_dump()
        if request.extracted_requirements is not None
        else None
    )
    async with session.begin():
        job = await JobRepository(session).create(
            user_id=current_user.id,
            raw_description=request.job_description,
            title=request.title,
            company_name=request.company_name,
            extracted_requirements=requirements,
        )

    payload = success_response(data=_job_detail(job))
    payload["code"] = status.HTTP_201_CREATED
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=payload,
    )


@router.get("")
async def list_jobs_endpoint(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("jobs_list")
    ),
) -> dict:
    """查询当前用户的岗位列表。"""

    jobs = await JobRepository(session).list_for_user(
        current_user.id
    )
    return success_response(
        data=[_job_summary(job) for job in jobs]
    )


@router.get("/{job_id}")
async def get_job_endpoint(
    job_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("jobs_read")
    ),
) -> dict:
    """查询当前用户的一个岗位。"""

    job = await JobRepository(session).get_for_user(
        job_id=job_id,
        user_id=current_user.id,
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="岗位不存在或无权访问",
        )

    return success_response(data=_job_detail(job))


@router.patch("/{job_id}")
async def update_job_endpoint(
    job_id: int,
    request: JobUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("jobs_update")
    ),
) -> dict:
    """编辑当前用户的岗位字段。"""

    updates = request.model_dump(exclude_unset=True)
    if "job_description" in updates:
        updates["raw_description"] = updates.pop("job_description")

    async with session.begin():
        repository = JobRepository(session)
        job = await repository.get_for_user(
            job_id=job_id,
            user_id=current_user.id,
            for_update=True,
        )
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="岗位不存在或无权访问",
            )
        if updates:
            job = await repository.update(job, **updates)

    return success_response(data=_job_detail(job))


@router.delete("/{job_id}")
async def delete_job_endpoint(
    job_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("jobs_delete")
    ),
) -> dict:
    """软删除当前用户的岗位。"""

    async with session.begin():
        repository = JobRepository(session)
        job = await repository.get_for_user(
            job_id=job_id,
            user_id=current_user.id,
            for_update=True,
        )
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="岗位不存在或无权访问",
            )
        await repository.soft_delete(job)

    return success_response(
        data=JobDeleteResponse(job_id=job_id)
    )


@router.post("/extract")
async def extract_job_endpoint(
    request: JobExtractionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("jobs_extract")
    ),
) -> dict:
    """提取岗位 JD 的结构化要求。"""

    usage_token = start_usage_collection()
    try:
        result = await extract_job(request.job_description)
    finally:
        usage_records = finish_usage_collection(usage_token)
        total_tokens = sum(
            record.total_tokens for record in usage_records
        )
        if total_tokens > 0:
            await record_daily_token_usage(
                get_redis_client(),
                user_id=current_user.id,
                total_tokens=total_tokens,
            )
    return success_response(data=result)


__all__ = ["router"]
