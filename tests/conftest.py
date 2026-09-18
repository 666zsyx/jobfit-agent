import os

import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LLM_API_KEY", "test-api-key")
os.environ.setdefault("LLM_BASE_URL", "https://example.invalid")
os.environ.setdefault("LLM_MODEL", "test-model")


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer demo-token"}
