# 提供最小演示账号登录和 JWT 用户接口。

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.client import get_redis_client
from app.core.config import settings
from app.core.response import success_response
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db_session
from app.repositories import UserRepository
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    TokenResponse,
)
from app.services.auth import (
    create_access_token,
    verify_demo_credentials,
)
from app.services.rate_limit import enforce_login_rate_limit


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="用户名或密码错误",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login")
async def login_endpoint(
    request: LoginRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """校验演示账号并签发 JWT。"""

    client_ip = (
        http_request.client.host
        if http_request.client is not None
        else "unknown"
    )
    await enforce_login_rate_limit(
        get_redis_client(),
        client_ip=client_ip,
        username=request.username,
    )

    if not verify_demo_credentials(
        request.username,
        request.password,
    ):
        raise _invalid_credentials()

    user = await UserRepository(session).get_by_username(
        settings.demo_username
    )
    if user is None or user.status != "active":
        raise _invalid_credentials()

    current_user = CurrentUser(
        id=user.user_id,
        username=user.username,
        role=user.role,
    )
    access_token = create_access_token(current_user)
    return success_response(
        data=TokenResponse(
            access_token=access_token,
            expires_in=settings.auth_jwt_expire_minutes * 60,
            user=current_user,
        )
    )


@router.get("/me")
async def get_me_endpoint(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """返回 JWT 或开发 Token 解析出的当前用户。"""

    return success_response(data=current_user)


__all__ = ["router"]
