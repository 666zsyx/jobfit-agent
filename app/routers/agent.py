# 提供 JobFit ReAct Agent 的 HTTP 接口。

from fastapi import APIRouter, Depends

from app.core.response import success_response
from app.dependencies.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.react_agent import JobFitAgentRequest
from app.services.react_agent import run_jobfit_agent
from app.tools import ToolContext


router = APIRouter(prefix="/api/agent", tags=["agent"])


# 运行一次受控的 JobFit ReAct 分析。
@router.post("/match")
async def match_jobfit_agent(
    request: JobFitAgentRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    context = ToolContext(current_user=current_user)

    result = await run_jobfit_agent(
        job_description=request.job_description,
        resume_text=request.resume_text,
        context=context,
    )

    return success_response(data=result)