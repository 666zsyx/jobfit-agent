import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    app_env: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str

def get_settings() -> Settings:
    app_env = os.getenv("APP_ENV","development")
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    if not api_key or not base_url or not model:
        raise RuntimeError("LLM 配置不完整，请检查 .env")
    settings = Settings(
        app_env=app_env,
        llm_api_key=api_key,
        llm_base_url=base_url,
        llm_model=model
    )
    return settings

settings = get_settings()


