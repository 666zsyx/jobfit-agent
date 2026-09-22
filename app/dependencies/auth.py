# 提供当前演示环境下的 Bearer 鉴权依赖。

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.auth import CurrentUser

security = HTTPBearer(auto_error=False)


# 校验演示 Bearer Token，并返回后端可信的当前用户。
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供身份验证凭证",
        )

    if credentials.credentials != "demo-token":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Token",
        )

    return CurrentUser(
        id=1,
        username="demo_user",
        role="admin",
    )