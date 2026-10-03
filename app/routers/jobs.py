# 提供岗位 JD 结构化提取接口。

from fastapi import APIRouter, Depends

from app.cache.client import get_redis_client
from app.core.cost_tracking import (
    finish_usage_collection,
    start_usage_collection,
)
from app.core.response import success_response
from app.dependencies.rate_limit import make_rate_limit_dependency
from app.dependencies.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.extraction import JobExtractionRequest
from app.services.extraction import extract_job
from app.services.rate_limit import record_daily_token_usage

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# 接收岗位 JD，调用提取服务并返回结构化结果。
@router.post("/extract")
async def extract_job_endpoint(
    request: JobExtractionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("jobs_extract")
    ),
) -> dict:
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
