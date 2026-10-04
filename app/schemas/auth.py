# 定义认证接口和当前用户的数据结构。

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CurrentUser(BaseModel):
    """后端鉴权后确认的当前用户。"""

    id: int
    username: str
    role: str


class LoginRequest(BaseModel):
    """演示账号登录请求。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("用户名不能为空")
        return value


class TokenResponse(BaseModel):
    """JWT 登录响应。"""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
    user: CurrentUser


__all__ = [
    "CurrentUser",
    "LoginRequest",
    "TokenResponse",
]
