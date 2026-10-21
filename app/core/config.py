# 读取并校验应用、LLM、数据库和 RAG 配置。

import os

from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv()


ALLOWED_APP_ENVS = {"development", "test", "staging", "production"}
SECURE_APP_ENVS = {"staging", "production"}


class Settings(BaseModel):
    """应用运行所需的配置字段。"""

    app_env: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    database_url: str
    redis_url: str
    embedding_model_name: str
    embedding_cache_path: str
    vector_index_path: str
    vector_collection_name: str
    reranker_model_name: str
    jobfit_confirmation_policy: str
    rate_limit_enabled: bool
    rate_limit_requests_per_minute: int
    daily_request_quota: int
    daily_token_quota: int
    auth_jwt_secret: str
    auth_jwt_expire_minutes: int
    demo_username: str
    demo_password: str
    demo_access_token: str
    allow_demo_token: bool


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} 必须是整数") from exc
    if value <= 0:
        raise RuntimeError(f"{name} 必须大于 0")
    return value


def get_settings() -> Settings:
    """从环境变量读取配置，缺少关键配置时立即失败。"""

    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env not in ALLOWED_APP_ENVS:
        raise RuntimeError(
            "APP_ENV 必须是 development、test、staging 或 production"
        )
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    database_url = os.getenv("DATABASE_URL")
    redis_url = os.getenv("REDIS_URL")
    embedding_model_name = os.getenv(
        "EMBEDDING_MODEL_NAME",
        "BAAI/bge-small-zh-v1.5",
    )
    embedding_cache_path = os.getenv(
        "EMBEDDING_CACHE_PATH",
        ".cache/fastembed",
    )
    vector_index_path = os.getenv(
        "VECTOR_INDEX_PATH",
        ".cache/chroma",
    )
    vector_collection_name = os.getenv(
        "VECTOR_COLLECTION_NAME",
        "jobfit_resume_chunks_v1",
    )
    reranker_model_name = os.getenv(
        "RERANKER_MODEL_NAME",
        "BAAI/bge-reranker-base",
    )
    confirmation_policy = os.getenv(
        "JOBFIT_CONFIRMATION_POLICY",
        "risk_based",
    ).strip().lower()
    if confirmation_policy not in {"always", "risk_based"}:
        raise RuntimeError(
            "JOBFIT_CONFIRMATION_POLICY 必须是 always 或 risk_based"
        )
    rate_limit_enabled = _env_bool("RATE_LIMIT_ENABLED", True)
    rate_limit_requests_per_minute = _env_int(
        "RATE_LIMIT_REQUESTS_PER_MINUTE",
        60,
    )
    daily_request_quota = _env_int("DAILY_REQUEST_QUOTA", 200)
    daily_token_quota = _env_int("DAILY_TOKEN_QUOTA", 200_000)
    auth_jwt_secret = os.getenv("AUTH_JWT_SECRET", "").strip()
    if not auth_jwt_secret:
        if app_env in SECURE_APP_ENVS:
            raise RuntimeError("staging/production 必须配置 AUTH_JWT_SECRET")
        auth_jwt_secret = "dev-only-jobfit-jwt-secret-change-me"
    auth_jwt_expire_minutes = _env_int(
        "AUTH_JWT_EXPIRE_MINUTES",
        1440,
    )
    demo_username = (
        os.getenv("DEMO_USERNAME", "demo_user").strip()
        or "demo_user"
    )
    demo_password = os.getenv("DEMO_PASSWORD", "demo-password")
    demo_access_token = os.getenv(
        "DEMO_ACCESS_TOKEN",
        "demo-token",
    )
    allow_demo_token = _env_bool(
        "ALLOW_DEMO_TOKEN",
        app_env not in SECURE_APP_ENVS,
    )

    if app_env in SECURE_APP_ENVS:
        if len(auth_jwt_secret) < 32:
            raise RuntimeError("staging/production AUTH_JWT_SECRET 至少需要 32 个字符")
        if demo_password == "demo-password" or len(demo_password) < 12:
            raise RuntimeError("staging/production 必须配置强 DEMO_PASSWORD")
        if allow_demo_token:
            raise RuntimeError("staging/production 必须禁用 ALLOW_DEMO_TOKEN")

    if not api_key or not base_url or not model:
        raise RuntimeError("LLM 配置不完整，请检查 .env")

    if not database_url:
        raise RuntimeError("数据库配置不完整，请检查 .env")

    if not redis_url:
        raise RuntimeError("Redis 配置不完整，请检查 .env")

    return Settings(
        app_env=app_env,
        llm_api_key=api_key,
        llm_base_url=base_url,
        llm_model=model,
        database_url=database_url,
        redis_url=redis_url,
        embedding_model_name=embedding_model_name,
        embedding_cache_path=embedding_cache_path,
        vector_index_path=vector_index_path,
        vector_collection_name=vector_collection_name,
        reranker_model_name=reranker_model_name,
        jobfit_confirmation_policy=confirmation_policy,
        rate_limit_enabled=rate_limit_enabled,
        rate_limit_requests_per_minute=rate_limit_requests_per_minute,
        daily_request_quota=daily_request_quota,
        daily_token_quota=daily_token_quota,
        auth_jwt_secret=auth_jwt_secret,
        auth_jwt_expire_minutes=auth_jwt_expire_minutes,
        demo_username=demo_username,
        demo_password=demo_password,
        demo_access_token=demo_access_token,
        allow_demo_token=allow_demo_token,
    )


settings = get_settings()
