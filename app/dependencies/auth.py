# 校验 Bearer Token，并解析当前用户。

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.schemas.auth import CurrentUser
from app.services.auth import (
    constant_time_text_equal,
    decode_access_token,
)

security = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    """校验 JWT；开发环境可选择兼容 demo-token。"""

    if credentials is None:
        raise _unauthorized("未提供身份验证凭证")

    token = credentials.credentials
    if settings.allow_demo_token and constant_time_text_equal(
        token,
        settings.demo_access_token,
    ):
        return CurrentUser(
            id=1,
            username=settings.demo_username,
            role="admin",
        )

    try:
        return decode_access_token(token)
    except ValueError as exc:
        raise _unauthorized("无效或已过期的 Token") from exc


__all__ = ["get_current_user"]
