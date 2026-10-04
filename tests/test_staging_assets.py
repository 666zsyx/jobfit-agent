# 验证私有 Linux staging 部署资产。

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_staging_env_template_is_safe():
    text = (PROJECT_ROOT / ".env.staging.example").read_text(
        encoding="utf-8"
    )

    assert "APP_ENV=staging" in text
    assert "ALLOW_DEMO_TOKEN=false" in text
    assert "AUTH_JWT_SECRET=" in text
    assert "JOBFIT_DB_PASSWORD=" in text


def test_caddy_terminates_https_for_agent():
    text = (PROJECT_ROOT / "deploy" / "Caddyfile").read_text(
        encoding="utf-8"
    )

    assert "{$DOMAIN}" in text
    assert "reverse_proxy jobfit-agent:8000" in text
    assert "Strict-Transport-Security" in text


def test_staging_compose_adds_caddy():
    text = (PROJECT_ROOT / "docker-compose.staging.yml").read_text(
        encoding="utf-8"
    )

    assert "caddy:2-alpine" in text
    assert '"80:80"' in text
    assert '"443:443"' in text
    assert "jobfit-agent" in text


def test_shell_scripts_are_linux_safe():
    for name in (
        "deploy_staging.sh",
        "seed_staging.sh",
        "backup_postgres.sh",
    ):
        path = PROJECT_ROOT / "scripts" / name
        raw = path.read_bytes()
        assert b"\r\n" not in raw
        assert raw.startswith(b"#!/usr/bin/env bash")
