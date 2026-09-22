# 提供当前用户信息接口，用于验证鉴权链路。

from fastapi import APIRouter, Depends

from app.core.response import success_response
from app.dependencies.auth import get_current_user
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/api/users", tags=["users"])


# 返回鉴权依赖解析出的当前用户信息。
@router.get("/me")
async def get_me(
    user: CurrentUser = Depends(get_current_user),
):
    return success_response(data=user)