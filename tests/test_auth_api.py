# 验证最小 JWT 登录、签发和鉴权链路。

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt

from app.core.config import settings
from app.dependencies import auth as auth_dependency
from app.routers import auth as auth_router
from app.schemas.auth import CurrentUser
from app.services.auth import (
    create_access_token,
    decode_access_token,
)


def make_user() -> SimpleNamespace:
    return SimpleNamespace(
        user_id=7,
        username=settings.demo_username,
        role="admin",
        status="active",
    )


def test_login_requires_valid_request(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "demo_user"},
    )

    assert response.status_code == 422


def test_login_rejects_wrong_password(client):
    response = client.post(
        "/api/auth/login",
        json={
            "username": settings.demo_username,
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["message"] == "用户名或密码错误"
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_returns_jwt_for_demo_account(
    client,
    monkeypatch,
):
    calls = []

    class FakeUserRepository:
        def __init__(self, session):
            pass

        async def get_by_username(self, username):
            calls.append(username)
            return make_user()

    monkeypatch.setattr(
        auth_router,
        "UserRepository",
        FakeUserRepository,
    )

    response = client.post(
        "/api/auth/login",
        json={
            "username": f"  {settings.demo_username}  ",
            "password": settings.demo_password,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == settings.auth_jwt_expire_minutes * 60
    assert data["user"] == {
        "id": 7,
        "username": settings.demo_username,
        "role": "admin",
    }
    token_user = decode_access_token(data["access_token"])
    assert token_user.id == 7
    assert token_user.username == settings.demo_username
    assert calls == [settings.demo_username]


def test_login_rejects_missing_or_disabled_user(
    client,
    monkeypatch,
):
    class FakeUserRepository:
        def __init__(self, session):
            pass

        async def get_by_username(self, username):
            return SimpleNamespace(
                user_id=7,
                username=username,
                role="admin",
                status="disabled",
            )

    monkeypatch.setattr(
        auth_router,
        "UserRepository",
        FakeUserRepository,
    )

    response = client.post(
        "/api/auth/login",
        json={
            "username": settings.demo_username,
            "password": settings.demo_password,
        },
    )

    assert response.status_code == 401
    assert response.json()["message"] == "用户名或密码错误"


def test_auth_me_accepts_jwt(client):
    token = create_access_token(
        CurrentUser(id=7, username="jwt_user", role="admin")
    )

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "id": 7,
        "username": "jwt_user",
        "role": "admin",
    }


def test_existing_user_endpoint_accepts_jwt(client):
    token = create_access_token(
        CurrentUser(id=8, username="jwt_user", role="user")
    )

    response = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == 8


def test_invalid_and_expired_jwt_are_rejected(client):
    expired_payload = {
        "sub": "7",
        "username": "demo_user",
        "role": "admin",
        "iat": int(
            (datetime.now(timezone.utc) - timedelta(minutes=2)).timestamp()
        ),
        "exp": int(
            (datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()
        ),
    }
    expired_token = jwt.encode(
        expired_payload,
        settings.auth_jwt_secret,
        algorithm="HS256",
    )

    expired_response = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    invalid_response = client.get(
        "/api/users/me",
        headers={"Authorization": "Bearer not-a-jwt"},
    )

    assert expired_response.status_code == 401
    assert invalid_response.status_code == 401
    assert expired_response.json()["message"] == "无效或已过期的 Token"
    assert invalid_response.json()["message"] == "无效或已过期的 Token"


def test_demo_token_is_allowed_in_test_environment(
    client,
    auth_headers,
):
    response = client.get(
        "/api/users/me",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["username"] == settings.demo_username


def test_demo_token_can_be_disabled(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        auth_dependency.settings,
        "allow_demo_token",
        False,
    )

    response = client.get(
        "/api/users/me",
        headers={"Authorization": "Bearer demo-token"},
    )

    assert response.status_code == 401
    assert response.json()["message"] == "无效或已过期的 Token"

def test_login_rejects_non_ascii_credentials(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "中文", "password": "中文"},
    )

    assert response.status_code == 401
    assert response.json()["message"] == "用户名或密码错误"
