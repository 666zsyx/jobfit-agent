# 检查生产部署所需配置，不输出任何密钥值。

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


REQUIRED_KEYS = [
    "APP_ENV",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "DATABASE_URL",
    "REDIS_URL",
]

PRODUCTION_AUTH_KEYS = [
    "AUTH_JWT_SECRET",
    "DEMO_USERNAME",
    "DEMO_PASSWORD",
]


def check_config() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for key in REQUIRED_KEYS:
        if not os.getenv(key, "").strip():
            errors.append(f"缺少配置：{key}")

    app_env = os.getenv("APP_ENV", "development").strip().lower()
    api_key = os.getenv("LLM_API_KEY", "")
    database_url = os.getenv("DATABASE_URL", "")
    redis_url = os.getenv("REDIS_URL", "")
    rate_limit_enabled = os.getenv(
        "RATE_LIMIT_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}
    log_format = os.getenv("LOG_FORMAT", "text").strip().lower()

    if app_env not in {"development", "test", "staging", "production"}:
        errors.append("APP_ENV 必须是 development、test、staging 或 production")

    if app_env in {"staging", "production"}:
        if "CHANGE_ME" in database_url or "CHANGE_ME" in api_key:
            errors.append("生产环境仍包含 CHANGE_ME 占位符")

        for key in PRODUCTION_AUTH_KEYS:
            if not os.getenv(key, "").strip():
                errors.append(f"生产环境缺少认证配置：{key}")

        jwt_secret = os.getenv("AUTH_JWT_SECRET", "").strip()
        demo_password = os.getenv("DEMO_PASSWORD", "").strip()
        allow_demo_token = os.getenv(
            "ALLOW_DEMO_TOKEN",
            "false",
        ).strip().lower() in {"1", "true", "yes", "on"}

        if jwt_secret and (
            len(jwt_secret) < 32
            or "CHANGE_ME" in jwt_secret
            or jwt_secret.startswith("dev-only")
        ):
            errors.append("AUTH_JWT_SECRET 必须使用至少 32 位强随机值")
        if demo_password and (
            len(demo_password) < 12
            or demo_password == "demo-password"
            or "CHANGE_ME" in demo_password
        ):
            errors.append("DEMO_PASSWORD 必须使用强密码")
        if allow_demo_token:
            errors.append("生产环境必须设置 ALLOW_DEMO_TOKEN=false")
        if not rate_limit_enabled:
            errors.append("生产环境必须启用限流")
        if log_format != "json":
            warnings.append("生产环境建议使用 LOG_FORMAT=json")
        if os.getenv("LLM_INPUT_PRICE_PER_1M", "0") == "0":
            warnings.append("未配置 LLM 输入 Token 价格")
        if os.getenv("LLM_OUTPUT_PRICE_PER_1M", "0") == "0":
            warnings.append("未配置 LLM 输出 Token 价格")

    if not database_url.startswith("postgresql+asyncpg://"):
        errors.append("DATABASE_URL 必须使用 postgresql+asyncpg")
    if not redis_url.startswith("redis://"):
        errors.append("REDIS_URL 必须使用 redis://")

    return errors, warnings


async def check_dependencies() -> dict[str, str]:
    from app.services.readiness import collect_readiness

    return await collect_readiness()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--connect", action="store_true")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    errors, warnings = check_config()
    report = {
        "errors": errors,
        "warnings": warnings,
        "ready": not errors,
    }

    if args.connect:
        from app.core.event_loop import configure_event_loop_policy
        import asyncio

        configure_event_loop_policy()
        dependencies = asyncio.run(check_dependencies())
        report["dependencies"] = dependencies
        if dependencies.get("status") != "ready":
            errors.append("依赖检查未就绪")

    report["ready"] = not errors
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors or (args.strict and warnings):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
