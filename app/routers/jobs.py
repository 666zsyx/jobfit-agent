# 提供岗位 JD 结构化提取接口。

from fastapi import APIRouter, Depends

from app.core.response import success_response
from app.dependencies.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.extraction import JobExtractionRequest
from app.services.extraction import extract_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# 接收岗位 JD，调用提取服务并返回结构化结果。
@router.post("/extract")
async def extract_job_endpoint(
    request: JobExtractionRequest,
    _current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    result = await extract_job(request.job_description)
    return success_response(data=result)
