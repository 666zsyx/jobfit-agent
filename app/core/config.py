# 读取并校验应用、LLM 和数据库连接配置。

import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# 应用运行所需的配置字段。
class Settings(BaseModel):
    app_env: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    database_url: str
    redis_url: str

# 从环境变量读取配置，缺少关键配置时立即失败。
def get_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "development")
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    database_url = os.getenv("DATABASE_URL")
    redis_url = os.getenv("REDIS_URL")

    if not api_key or not base_url or not model:
        raise RuntimeError("LLM 配置不完整，请检查 .env")

    if not database_url:
        raise RuntimeError("数据库配置不完整，请检查 .env")

    if not redis_url:
        raise RuntimeError("Redis 配置不完整，请检查 .env")

    settings = Settings(
        app_env=app_env,
        llm_api_key=api_key,
        llm_base_url=base_url,
        llm_model=model,
        database_url=database_url,
        redis_url=redis_url,
    )
    return settings


settings = get_settings()
