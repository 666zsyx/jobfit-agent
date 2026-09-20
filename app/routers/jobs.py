from fastapi import APIRouter, Depends

from app.core.response import success_response
from app.dependencies.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.extraction import JobExtractionRequest
from app.services.extraction import extract_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/extract")
async def extract_job_endpoint(
    request: JobExtractionRequest,
    _current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    result = await extract_job(request.job_description)
    return success_response(data=result)
