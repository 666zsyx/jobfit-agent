# 验证安全环境配置规范化与生产约束。


import pytest

from app.core.config import get_settings


def test_app_env_is_normalized_and_secure(
    monkeypatch,
):
    monkeypatch.setenv("APP_ENV", "Production")
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
        get_settings()


def test_staging_rejects_default_demo_password(
    monkeypatch,
):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv(
        "AUTH_JWT_SECRET",
        "a" * 32,
    )
    monkeypatch.setenv("DEMO_PASSWORD", "demo-password")
    monkeypatch.setenv("ALLOW_DEMO_TOKEN", "false")

    with pytest.raises(RuntimeError, match="DEMO_PASSWORD"):
        get_settings()

def test_deployment_check_normalizes_and_rejects_unknown_env(
    monkeypatch,
):
    from scripts.check_deployment_config import check_config

    monkeypatch.setenv("APP_ENV", "Production")
    errors, _ = check_config()
    assert "AUTH_JWT_SECRET" in "\n".join(errors)


def test_deployment_check_rejects_unknown_app_env(monkeypatch):
    from scripts.check_deployment_config import check_config

    monkeypatch.setenv("APP_ENV", "typo")
    errors, _ = check_config()
    assert any("APP_ENV" in error for error in errors)
