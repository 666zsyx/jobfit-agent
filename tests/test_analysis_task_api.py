# 验证持久化分析任务 API 的 Schema、响应和错误映射。

from types import SimpleNamespace

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.exceptions import LLMServiceError, TaskStateConflictError
from app.routers import agent as agent_router
from app.schemas.analysis_task_api import (
    GraphTaskExecutionResult,
    PersistedAgentExecutionResult,
)
from app.schemas.chat import TokenUsage


def make_task() -> SimpleNamespace:
    return SimpleNamespace(
        task_id=10,
        status="pending",
        current_step=0,
        attempt=0,
        max_steps=8,
        current_node=None,
    )


def make_execution_result() -> PersistedAgentExecutionResult:
    return PersistedAgentExecutionResult(
        task_id=10,
        status="completed",
        answer="匹配分析完成。",
        steps=3,
        max_steps=8,
        usage=TokenUsage(
            prompt_tokens=30,
            completion_tokens=10,
            total_tokens=40,
        ),
        latency_ms=500,
        report_id=20,
        report_version=1,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"job_id": 0, "resume_version_id": 1},
        {"job_id": 1, "resume_version_id": 0},
        {"job_id": 1, "resume_version_id": 1, "conversation_id": 0},
        {"job_id": 1, "resume_version_id": 1, "user_id": 99},
    ],
)
def test_create_task_validates_request(client, auth_headers, payload):
    response = client.post(
        "/api/agent/tasks",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["code"] == 422


def test_create_task_returns_201_response(
    client,
    auth_headers,
    monkeypatch,
):
    calls = []
    cache_calls = []

    async def fake_create_persisted_task(session, **kwargs):
        calls.append(kwargs)
        return make_task()

    async def fake_cache_task_status(redis, **kwargs):
        cache_calls.append(kwargs)

    monkeypatch.setattr(
        agent_router,
        "create_persisted_task",
        fake_create_persisted_task,
    )
    monkeypatch.setattr(
        agent_router,
        "cache_task_status",
        fake_cache_task_status,
    )

    response = client.post(
        "/api/agent/tasks",
        headers=auth_headers,
        json={
            "job_id": 1,
            "resume_version_id": 2,
            "conversation_id": 3,
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "code": 201,
        "message": "success",
        "data": {
            "task_id": 10,
            "status": "pending",
            "current_step": 0,
            "attempt": 0,
            "max_steps": 8,
            "current_node": None,
        },
    }
    assert calls == [
        {
            "user_id": 1,
            "job_id": 1,
            "resume_version_id": 2,
            "conversation_id": 3,
        }
    ]
    assert cache_calls == [
        {
            "user_id": 1,
            "task_id": 10,
            "status": "pending",
            "current_step": 0,
            "attempt": 0,
            "max_steps": 8,
            "current_node": None,
        }
    ]


def test_run_task_returns_execution_result(
    client,
    auth_headers,
    monkeypatch,
):
    calls = []
    expected = make_execution_result()

    async def fake_run_persisted_task(session, **kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr(
        agent_router,
        "run_persisted_task",
        fake_run_persisted_task,
    )

    response = client.post(
        "/api/agent/tasks/10/run",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "message": "success",
        "data": expected.model_dump(mode="json"),
    }
    assert calls[0]["user_id"] == 1
    assert calls[0]["task_id"] == 10
    assert "redis_client" in calls[0]


def test_create_task_maps_lookup_error_to_404(
    client,
    auth_headers,
    monkeypatch,
):
    async def fake_create_persisted_task(session, **kwargs):
        raise LookupError("资源不存在或无权访问")

    monkeypatch.setattr(
        agent_router,
        "create_persisted_task",
        fake_create_persisted_task,
    )

    response = client.post(
        "/api/agent/tasks",
        headers=auth_headers,
        json={"job_id": 1, "resume_version_id": 2},
    )

    assert response.status_code == 404
    assert response.json() == {
        "code": 404,
        "message": "资源不存在或无权访问",
        "data": None,
    }


def test_run_task_maps_lookup_error_to_404(
    client,
    auth_headers,
    monkeypatch,
):
    async def fake_run_persisted_task(session, **kwargs):
        raise LookupError("任务不存在或无权访问")

    monkeypatch.setattr(
        agent_router,
        "run_persisted_task",
        fake_run_persisted_task,
    )

    response = client.post(
        "/api/agent/tasks/10/run",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "任务不存在或无权访问"


def test_run_task_maps_state_conflict_to_409(
    client,
    auth_headers,
    monkeypatch,
):
    async def fake_run_persisted_task(session, **kwargs):
        raise TaskStateConflictError("任务状态 completed 不允许执行")

    monkeypatch.setattr(
        agent_router,
        "run_persisted_task",
        fake_run_persisted_task,
    )

    response = client.post(
        "/api/agent/tasks/10/run",
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": 409,
        "message": "任务状态 completed 不允许执行",
        "data": None,
    }


def test_run_task_propagates_service_error(
    client,
    auth_headers,
    monkeypatch,
):
    async def fake_run_persisted_task(session, **kwargs):
        raise LLMServiceError(
            message="LLM 请求超时，请稍后重试。",
            status_code=504,
        )

    monkeypatch.setattr(
        agent_router,
        "run_persisted_task",
        fake_run_persisted_task,
    )

    response = client.post(
        "/api/agent/tasks/10/run",
        headers=auth_headers,
    )

    assert response.status_code == 504
    assert response.json() == {
        "code": 504,
        "message": "LLM 请求超时，请稍后重试。",
        "data": None,
    }


def test_get_task_returns_cache_hit_without_database(
    client,
    auth_headers,
    monkeypatch,
):
    async def fake_get_cached_task_status(redis, **kwargs):
        return {
            "task_id": 10,
            "status": "running",
            "current_step": 2,
            "attempt": 1,
            "max_steps": 8,
            "current_node": None,
        }

    monkeypatch.setattr(
        agent_router,
        "get_cached_task_status",
        fake_get_cached_task_status,
    )

    response = client.get(
        "/api/agent/tasks/10",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "task_id": 10,
        "status": "running",
        "current_step": 2,
        "attempt": 1,
        "max_steps": 8,
        "current_node": None,
    }


def test_get_task_cache_miss_reads_database_and_backfills_cache(
    client,
    auth_headers,
    monkeypatch,
):
    cache_calls = []

    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, *, task_id, user_id):
            assert task_id == 10
            assert user_id == 1
            return make_task()

    async def fake_get_cached_task_status(redis, **kwargs):
        return None

    async def fake_cache_task_status(redis, **kwargs):
        cache_calls.append(kwargs)

    monkeypatch.setattr(
        agent_router,
        "AnalysisTaskRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        agent_router,
        "get_cached_task_status",
        fake_get_cached_task_status,
    )
    monkeypatch.setattr(
        agent_router,
        "cache_task_status",
        fake_cache_task_status,
    )

    response = client.get(
        "/api/agent/tasks/10",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "task_id": 10,
        "status": "pending",
        "current_step": 0,
        "attempt": 0,
        "max_steps": 8,
        "current_node": None,
    }
    assert cache_calls == [
        {
            "user_id": 1,
            "task_id": 10,
            "status": "pending",
            "current_step": 0,
            "attempt": 0,
            "max_steps": 8,
            "current_node": None,
        }
    ]


def test_get_task_cache_error_falls_back_to_database(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, *, task_id, user_id):
            return make_task()

    async def failing_cache_read(redis, **kwargs):
        raise RedisConnectionError("redis unavailable")

    async def fake_cache_task_status(redis, **kwargs):
        return None

    monkeypatch.setattr(
        agent_router,
        "AnalysisTaskRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        agent_router,
        "get_cached_task_status",
        failing_cache_read,
    )
    monkeypatch.setattr(
        agent_router,
        "cache_task_status",
        fake_cache_task_status,
    )

    response = client.get(
        "/api/agent/tasks/10",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["task_id"] == 10


def test_get_task_returns_404_when_not_owned(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, *, task_id, user_id):
            return None

    async def fake_get_cached_task_status(redis, **kwargs):
        return None

    monkeypatch.setattr(
        agent_router,
        "AnalysisTaskRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        agent_router,
        "get_cached_task_status",
        fake_get_cached_task_status,
    )

    response = client.get(
        "/api/agent/tasks/10",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "任务不存在或无权访问"


def test_run_graph_task_endpoint_returns_result(
    client,
    auth_headers,
    monkeypatch,
):
    calls = []

    async def fake_run_graph_persisted_task(session_factory, **kwargs):
        calls.append(kwargs)
        return GraphTaskExecutionResult(
            task_id=10,
            status="waiting_confirmation",
            current_node="human_confirmation",
            current_step=2,
            interrupted=True,
            pending_confirmation={"summary": "待确认"},
        )

    monkeypatch.setattr(
        agent_router,
        "run_graph_persisted_task",
        fake_run_graph_persisted_task,
    )

    response = client.post(
        "/api/agent/tasks/10/graph/run",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "waiting_confirmation"
    assert response.json()["data"]["current_node"] == "human_confirmation"
    assert calls[0]["user_id"] == 1
    assert calls[0]["task_id"] == 10


def test_resume_graph_task_endpoint_passes_revision(
    client,
    auth_headers,
    monkeypatch,
):
    calls = []

    async def fake_resume_graph_persisted_task(session_factory, **kwargs):
        calls.append(kwargs)
        return GraphTaskExecutionResult(
            task_id=10,
            status="completed",
            current_node="finalize",
            current_step=2,
            report_id=99,
            report_version=1,
            new_resume_version_id=101,
        )

    monkeypatch.setattr(
        agent_router,
        "resume_graph_persisted_task",
        fake_resume_graph_persisted_task,
    )

    response = client.post(
        "/api/agent/tasks/10/graph/resume",
        headers=auth_headers,
        json={
            "decision": "revise",
            "edited_report": {
                "summary": "确认后报告",
                "result_json": {"answer": "确认"},
            },
            "resume_revision_text": "修改后的简历",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"
    assert calls[0]["decision"] == "revise"
    assert calls[0]["resume_revision_text"] == "修改后的简历"


def test_resume_graph_task_requires_edited_content_for_revise(
    client,
    auth_headers,
):
    response = client.post(
        "/api/agent/tasks/10/graph/resume",
        headers=auth_headers,
        json={"decision": "revise"},
    )

    assert response.status_code == 422


def test_get_graph_confirmation_endpoint_returns_pending(
    client,
    auth_headers,
    monkeypatch,
):
    async def fake_get_graph_task_confirmation(session_factory, **kwargs):
        assert kwargs["user_id"] == 1
        assert kwargs["task_id"] == 10
        return GraphTaskExecutionResult(
            task_id=10,
            status="waiting_confirmation",
            current_node="human_confirmation",
            current_step=2,
            interrupted=True,
            pending_confirmation={"summary": "待确认"},
        )

    monkeypatch.setattr(
        agent_router,
        "get_graph_task_confirmation",
        fake_get_graph_task_confirmation,
    )

    response = client.get(
        "/api/agent/tasks/10/graph/confirmation",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["interrupted"] is True
    assert response.json()["data"]["pending_confirmation"] == {
        "summary": "待确认"
    }
