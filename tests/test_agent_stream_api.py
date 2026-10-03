# 验证 Agent SSE HTTP 接口的事件顺序和媒体类型。

from types import SimpleNamespace

from app.routers import agent as agent_router
from app.schemas.agent_events import AgentEvent


def test_stream_task_returns_sse_events(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, *, task_id, user_id):
            return SimpleNamespace(task_id=task_id)

    async def fake_run_persisted_task(
        session_factory,
        *,
        user_id,
        task_id,
        redis_client,
        event_sink,
    ):
        await event_sink(
            AgentEvent(
                type="task_started",
                task_id=task_id,
                data={"status": "running"},
            )
        )
        await event_sink(
            AgentEvent(
                type="content",
                task_id=task_id,
                content="done",
            )
        )
        await event_sink(
            AgentEvent(
                type="task_completed",
                task_id=task_id,
                content="done",
                data={"status": "completed"},
            )
        )

    monkeypatch.setattr(
        agent_router,
        "AnalysisTaskRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        agent_router,
        "run_persisted_task",
        fake_run_persisted_task,
    )

    with client.stream(
        "GET",
        "/api/agent/tasks/10/stream",
        headers=auth_headers,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "text/event-stream"
        )
        body = "".join(response.iter_text())

    assert "event: task_started" in body
    assert "event: content" in body
    assert "event: task_completed" in body
    assert "event: done" in body
    assert "data: [DONE]" in body

def test_graph_stream_returns_sse_events(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, *, task_id, user_id):
            return SimpleNamespace(task_id=task_id)

    async def fake_run_graph_persisted_task(
        session_factory,
        *,
        user_id,
        task_id,
        redis_client,
        event_sink,
    ):
        await event_sink(
            AgentEvent(
                type="graph_started",
                task_id=task_id,
                data={"attempt": 1},
            )
        )
        await event_sink(
            AgentEvent(
                type="node_started",
                task_id=task_id,
                data={"node": "agent_decide"},
            )
        )
        await event_sink(
            AgentEvent(
                type="waiting_confirmation",
                task_id=task_id,
                data={"node": "human_confirmation"},
            )
        )

    monkeypatch.setattr(
        agent_router,
        "AnalysisTaskRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        agent_router,
        "run_graph_persisted_task",
        fake_run_graph_persisted_task,
    )

    with client.stream(
        "GET",
        "/api/agent/tasks/10/graph/stream",
        headers=auth_headers,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "text/event-stream"
        )
        body = "".join(response.iter_text())

    assert "event: graph_started" in body
    assert "event: node_started" in body
    assert "event: waiting_confirmation" in body
    assert "event: done" in body
