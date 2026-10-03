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


def check_config() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for key in REQUIRED_KEYS:
        if not os.getenv(key, "").strip():
            errors.append(f"缺少配置：{key}")

    app_env = os.getenv("APP_ENV", "development").strip()
    api_key = os.getenv("LLM_API_KEY", "")
    database_url = os.getenv("DATABASE_URL", "")
    redis_url = os.getenv("REDIS_URL", "")
    rate_limit_enabled = os.getenv(
        "RATE_LIMIT_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}
    log_format = os.getenv("LOG_FORMAT", "text").strip().lower()

    if app_env == "production":
        if "CHANGE_ME" in database_url or "CHANGE_ME" in api_key:
            errors.append("生产环境仍包含 CHANGE_ME 占位符")
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
        report["dependencies"] = asyncio.run(check_dependencies())

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors or (args.strict and warnings):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
