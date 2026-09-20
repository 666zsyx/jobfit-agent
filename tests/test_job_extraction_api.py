import pytest

from app.core.exceptions import LLMServiceError, StructuredOutputError
from app.routers import jobs as jobs_router
from app.schemas.extraction import JobExtraction


VALID_JOB_DESCRIPTION = "负责 FastAPI 后端开发"
LONG_JOB_DESCRIPTION = "a" * 20_001


def make_job_extraction() -> JobExtraction:
    return JobExtraction(
        responsibilities=["负责 FastAPI 后端服务开发"],
        required_skills=["熟悉 Python 和 FastAPI"],
        nice_to_have=["有 LLM 应用开发经验"],
    )


def test_extract_job_requires_auth(client, monkeypatch):
    calls = []

    async def fake_extract_job(job_description: str) -> JobExtraction:
        calls.append(job_description)
        return make_job_extraction()

    monkeypatch.setattr(jobs_router, "extract_job", fake_extract_job)

    response = client.post(
        "/api/jobs/extract",
        json={"job_description": VALID_JOB_DESCRIPTION},
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": 401,
        "message": "未提供身份验证凭证",
        "data": None,
    }
    assert calls == []


@pytest.mark.parametrize(
    "job_description",
    [
        "",
        "   ",
        LONG_JOB_DESCRIPTION,
    ],
)
def test_extract_job_validates_request(
    client,
    auth_headers,
    monkeypatch,
    job_description,
):
    calls = []

    async def fake_extract_job(job_description: str) -> JobExtraction:
        calls.append(job_description)
        return make_job_extraction()

    monkeypatch.setattr(jobs_router, "extract_job", fake_extract_job)

    response = client.post(
        "/api/jobs/extract",
        headers=auth_headers,
        json={"job_description": job_description},
    )

    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert response.json()["message"] == "请求参数校验失败"
    assert calls == []


def test_extract_job_returns_success_response(
    client,
    auth_headers,
    monkeypatch,
):
    calls = []

    async def fake_extract_job(job_description: str) -> JobExtraction:
        calls.append(job_description)
        return make_job_extraction()

    monkeypatch.setattr(jobs_router, "extract_job", fake_extract_job)

    response = client.post(
        "/api/jobs/extract",
        headers=auth_headers,
        json={"job_description": f"  {VALID_JOB_DESCRIPTION}  "},
    )

    assert response.status_code == 200
    assert calls == [VALID_JOB_DESCRIPTION]
    assert response.json() == {
        "code": 200,
        "message": "success",
        "data": {
            "responsibilities": ["负责 FastAPI 后端服务开发"],
            "required_skills": ["熟悉 Python 和 FastAPI"],
            "nice_to_have": ["有 LLM 应用开发经验"],
        },
    }


def test_extract_job_returns_structured_output_error(
    client,
    auth_headers,
    monkeypatch,
):
    calls = []

    async def fake_extract_job(job_description: str) -> JobExtraction:
        calls.append(job_description)
        raise StructuredOutputError(
            message="岗位 JD 结构化提取失败，请稍后重试。",
        )

    monkeypatch.setattr(jobs_router, "extract_job", fake_extract_job)

    response = client.post(
        "/api/jobs/extract",
        headers=auth_headers,
        json={"job_description": VALID_JOB_DESCRIPTION},
    )

    assert response.status_code == 502
    assert response.json() == {
        "code": 502,
        "message": "岗位 JD 结构化提取失败，请稍后重试。",
        "data": None,
    }
    assert calls == [VALID_JOB_DESCRIPTION]


def test_extract_job_returns_llm_service_error(
    client,
    auth_headers,
    monkeypatch,
):
    calls = []

    async def fake_extract_job(job_description: str) -> JobExtraction:
        calls.append(job_description)
        raise LLMServiceError(
            message="LLM 服务暂时不可用。",
            status_code=503,
        )

    monkeypatch.setattr(jobs_router, "extract_job", fake_extract_job)

    response = client.post(
        "/api/jobs/extract",
        headers=auth_headers,
        json={"job_description": VALID_JOB_DESCRIPTION},
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": 503,
        "message": "LLM 服务暂时不可用。",
        "data": None,
    }
    assert calls == [VALID_JOB_DESCRIPTION]
