# 验证任务历史列表和当前报告查询接口。

from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers import agent as agent_router


def make_report(
    *,
    report_id: int = 99,
    version_no: int = 1,
    deleted: bool = False,
) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        report_id=report_id,
        task_id=10,
        version_no=version_no,
        is_current=not deleted,
        summary="岗位匹配分析已完成。",
        result_json={
            "answer": "匹配度较高。",
            "evidence": [{"chunk_id": 101}],
        },
        created_at=now,
        updated_at=now,
        deleted_at=now if deleted else None,
    )


def make_task(
    *,
    reports: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        task_id=10,
        job_id=2,
        resume_version_id=20,
        conversation_id=None,
        job=SimpleNamespace(
            title="Python 后端开发",
            company_name="示例科技",
            raw_description="负责 FastAPI 服务和 Agent 应用开发。",
        ),
        resume_version=SimpleNamespace(
            resume=SimpleNamespace(title="我的简历")
        ),
        status="completed",
        current_step=3,
        attempt=0,
        max_steps=8,
        current_node="finalize",
        reports=reports if reports is not None else [make_report()],
        started_at=now,
        finished_at=now,
        created_at=now,
        updated_at=now,
    )


def test_list_tasks_requires_auth(client, monkeypatch):
    calls = []

    class FakeRepository:
        def __init__(self, session):
            pass

        async def list_for_user(self, *args, **kwargs):
            calls.append((args, kwargs))
            return [make_task()]

    monkeypatch.setattr(
        agent_router,
        "AnalysisTaskRepository",
        FakeRepository,
    )

    response = client.get("/api/agent/tasks")

    assert response.status_code == 401
    assert calls == []


def test_list_tasks_returns_context_and_report_summary(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeRepository:
        def __init__(self, session):
            pass

        async def list_for_user(
            self,
            user_id,
            with_relations=False,
        ):
            assert user_id == 1
            assert with_relations is True
            return [make_task()]

    monkeypatch.setattr(
        agent_router,
        "AnalysisTaskRepository",
        FakeRepository,
    )

    response = client.get(
        "/api/agent/tasks",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["task_id"] == 10
    assert data[0]["job_title"] == "Python 后端开发"
    assert data[0]["company_name"] == "示例科技"
    assert data[0]["resume_title"] == "我的简历"
    assert data[0]["status"] == "completed"
    assert data[0]["report_id"] == 99
    assert data[0]["report_version"] == 1


def test_list_tasks_handles_task_without_report(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeRepository:
        def __init__(self, session):
            pass

        async def list_for_user(self, *args, **kwargs):
            return [make_task(reports=[])]

    monkeypatch.setattr(
        agent_router,
        "AnalysisTaskRepository",
        FakeRepository,
    )

    response = client.get(
        "/api/agent/tasks",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"][0]
    assert data["report_id"] is None
    assert data["report_version"] is None


def test_list_tasks_skips_deleted_current_report(
    client,
    auth_headers,
    monkeypatch,
):
    reports = [
        make_report(report_id=90, version_no=1),
        make_report(
            report_id=91,
            version_no=2,
            deleted=True,
        ),
    ]

    class FakeRepository:
        def __init__(self, session):
            pass

        async def list_for_user(self, *args, **kwargs):
            return [make_task(reports=reports)]

    monkeypatch.setattr(
        agent_router,
        "AnalysisTaskRepository",
        FakeRepository,
    )

    response = client.get(
        "/api/agent/tasks",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"][0]["report_id"] == 90
    assert response.json()["data"][0]["report_version"] == 1


def test_get_task_report_returns_current_report(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_current_for_user(self, *, task_id, user_id):
            assert task_id == 10
            assert user_id == 1
            return make_report()

    monkeypatch.setattr(
        agent_router,
        "ReportRepository",
        FakeRepository,
    )

    response = client.get(
        "/api/agent/tasks/10/report",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["report_id"] == 99
    assert data["task_id"] == 10
    assert data["summary"] == "岗位匹配分析已完成。"
    assert data["result_json"]["evidence"] == [{"chunk_id": 101}]


def test_get_task_report_returns_404_when_missing(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_current_for_user(self, **kwargs):
            return None

    monkeypatch.setattr(
        agent_router,
        "ReportRepository",
        FakeRepository,
    )

    response = client.get(
        "/api/agent/tasks/10/report",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "报告不存在或尚未生成"


def test_get_task_report_requires_auth(client, monkeypatch):
    calls = []

    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_current_for_user(self, **kwargs):
            calls.append(kwargs)
            return make_report()

    monkeypatch.setattr(
        agent_router,
        "ReportRepository",
        FakeRepository,
    )

    response = client.get("/api/agent/tasks/10/report")

    assert response.status_code == 401
    assert calls == []
