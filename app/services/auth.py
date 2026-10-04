# 提供演示账号校验和 JWT 签发、解析能力。

from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError

from app.core.config import settings
from app.schemas.auth import CurrentUser


JWT_ALGORITHM = "HS256"
REQUIRED_CLAIMS = ["sub", "username", "role", "iat", "exp"]


def constant_time_text_equal(
    left: str,
    right: str,
) -> bool:
    """对中文等非 ASCII 文本也安全的常量时间比较。"""

    return hmac.compare_digest(
        left.encode("utf-8"),
        right.encode("utf-8"),
    )


def verify_demo_credentials(
    username: str,
    password: str,
) -> bool:
    """使用常量时间比较演示账号和密码。"""

    username_ok = constant_time_text_equal(
        username,
        settings.demo_username,
    )
    password_ok = constant_time_text_equal(
        password,
        settings.demo_password,
    )
    return username_ok and password_ok


def create_access_token(
    user: CurrentUser,
    *,
    expires_seconds: int | None = None,
) -> str:
    """为当前用户签发 HS256 JWT。"""

    lifetime_seconds = (
        expires_seconds
        if expires_seconds is not None
        else settings.auth_jwt_expire_minutes * 60
    )
    if lifetime_seconds <= 0:
        raise ValueError("JWT 有效期必须大于 0")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=lifetime_seconds)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(
        payload,
        settings.auth_jwt_secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> CurrentUser:
    """校验 JWT 并恢复后端可信的当前用户。"""

    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": REQUIRED_CLAIMS},
        )
        user_id = int(payload["sub"])
        username = str(payload["username"])
        role = str(payload["role"])
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("无效或已过期的 Token") from exc

    if user_id <= 0 or not username or not role:
        raise ValueError("Token 用户信息不完整")

    return CurrentUser(
        id=user_id,
        username=username,
        role=role,
    )


__all__ = [
    "constant_time_text_equal",
    "create_access_token",
    "decode_access_token",
    "verify_demo_credentials",
]
