# 验证 JobFit ReAct Agent HTTP 接口的鉴权、请求校验和响应结构。

import pytest

from app.core.exceptions import LLMServiceError
from app.routers import agent as agent_router
from app.schemas.chat import TokenUsage
from app.schemas.react_agent import (
    ReactAgentResult,
    ReactToolExecution,
)

VALID_JOB_DESCRIPTION = "负责 FastAPI 后端开发，要求熟悉 Python。"
VALID_RESUME_TEXT = "熟悉 Python 和 FastAPI，完成过课程项目。"
LONG_JOB_DESCRIPTION = "a" * 20_001
LONG_RESUME_TEXT = "a" * 50_001


def make_result() -> ReactAgentResult:
    return ReactAgentResult(
        answer=(
            "strong_match：熟悉 Python；"
            "partial_match：FastAPI 项目经验。"
        ),
        status="completed",
        steps=2,
        max_steps=8,
        trace=[
            ReactToolExecution(
                step=1,
                tool_call_id="call_001",
                tool_name="extract_job_requirements",
                arguments={"job_description": VALID_JOB_DESCRIPTION},
                result={
                    "ok": True,
                    "result": {
                        "responsibilities": ["负责 FastAPI 后端开发"],
                        "required_skills": ["熟悉 Python"],
                        "nice_to_have": [],
                    },
                },
            )
        ],
        usage=TokenUsage(
            prompt_tokens=30,
            completion_tokens=10,
            total_tokens=40,
        ),
        latency_ms=123,
    )


def test_match_requires_auth(client, monkeypatch):
    calls = []

    async def fake_run_jobfit_agent(**kwargs) -> ReactAgentResult:
        calls.append(kwargs)
        return make_result()

    monkeypatch.setattr(
        agent_router,
        "run_jobfit_agent",
        fake_run_jobfit_agent,
    )

    response = client.post(
        "/api/agent/match",
        json={
            "job_description": VALID_JOB_DESCRIPTION,
            "resume_text": VALID_RESUME_TEXT,
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": 401,
        "message": "未提供身份验证凭证",
        "data": None,
    }
    assert calls == []


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {
                "job_description": "",
                "resume_text": VALID_RESUME_TEXT,
            },
            id="blank-job",
        ),
        pytest.param(
            {
                "job_description": "   ",
                "resume_text": VALID_RESUME_TEXT,
            },
            id="whitespace-job",
        ),
        pytest.param(
            {
                "job_description": VALID_JOB_DESCRIPTION,
                "resume_text": "",
            },
            id="blank-resume",
        ),
        pytest.param(
            {
                "job_description": VALID_JOB_DESCRIPTION,
                "resume_text": "   ",
            },
            id="whitespace-resume",
        ),
        pytest.param(
            {"resume_text": VALID_RESUME_TEXT},
            id="missing-job",
        ),
        pytest.param(
            {"job_description": VALID_JOB_DESCRIPTION},
            id="missing-resume",
        ),
        pytest.param(
            {
                "job_description": LONG_JOB_DESCRIPTION,
                "resume_text": VALID_RESUME_TEXT,
            },
            id="long-job",
        ),
        pytest.param(
            {
                "job_description": VALID_JOB_DESCRIPTION,
                "resume_text": LONG_RESUME_TEXT,
            },
            id="long-resume",
        ),
        pytest.param(
            {
                "job_description": VALID_JOB_DESCRIPTION,
                "resume_text": VALID_RESUME_TEXT,
                "max_steps": 1,
            },
            id="client-controlled-max-steps",
        ),
    ],
)
def test_match_validates_request(
    client,
    auth_headers,
    monkeypatch,
    payload,
):
    calls = []

    async def fake_run_jobfit_agent(**kwargs) -> ReactAgentResult:
        calls.append(kwargs)
        return make_result()

    monkeypatch.setattr(
        agent_router,
        "run_jobfit_agent",
        fake_run_jobfit_agent,
    )

    response = client.post(
        "/api/agent/match",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert response.json()["message"] == "请求参数校验失败"
    assert calls == []


def test_match_returns_success_response(
    client,
    auth_headers,
    monkeypatch,
):
    calls = []

    async def fake_run_jobfit_agent(**kwargs) -> ReactAgentResult:
        calls.append(kwargs)
        return make_result()

    monkeypatch.setattr(
        agent_router,
        "run_jobfit_agent",
        fake_run_jobfit_agent,
    )

    response = client.post(
        "/api/agent/match",
        headers=auth_headers,
        json={
            "job_description": f"  {VALID_JOB_DESCRIPTION}  ",
            "resume_text": f"  {VALID_RESUME_TEXT}  ",
        },
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["job_description"] == VALID_JOB_DESCRIPTION
    assert calls[0]["resume_text"] == VALID_RESUME_TEXT
    assert calls[0]["context"].current_user.id == 1
    assert calls[0]["context"].current_user.username == "demo_user"
    assert "max_steps" not in calls[0]
    assert response.json() == {
        "code": 200,
        "message": "success",
        "data": make_result().model_dump(mode="json"),
    }


def test_match_maps_llm_service_error(
    client,
    auth_headers,
    monkeypatch,
):
    calls = []

    async def failing_run_jobfit_agent(**kwargs) -> ReactAgentResult:
        calls.append(kwargs)
        raise LLMServiceError(
            message="LLM 请求超时，请稍后重试。",
            status_code=504,
        )

    monkeypatch.setattr(
        agent_router,
        "run_jobfit_agent",
        failing_run_jobfit_agent,
    )

    response = client.post(
        "/api/agent/match",
        headers=auth_headers,
        json={
            "job_description": VALID_JOB_DESCRIPTION,
            "resume_text": VALID_RESUME_TEXT,
        },
    )

    assert response.status_code == 504
    assert response.json() == {
        "code": 504,
        "message": "LLM 请求超时，请稍后重试。",
        "data": None,
    }
    assert len(calls) == 1
