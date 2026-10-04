# 验证岗位持久化 API 的创建、查询、编辑和软删除行为。

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routers import jobs as jobs_router


def make_job() -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        job_id=10,
        user_id=1,
        title="Python 后端开发",
        company_name="示例科技",
        raw_description="负责 FastAPI 服务开发，要求熟悉 Python。",
        extracted_requirements={
            "responsibilities": ["负责 FastAPI 服务开发"],
            "required_skills": ["熟悉 Python"],
            "nice_to_have": [],
        },
        status="active",
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def test_create_job_requires_auth(client, monkeypatch):
    calls = []

    class FakeRepository:
        def __init__(self, session):
            pass

        async def create(self, **kwargs):
            calls.append(kwargs)
            return make_job()

    monkeypatch.setattr(jobs_router, "JobRepository", FakeRepository)

    response = client.post(
        "/api/jobs",
        json={"job_description": "负责 Python 服务开发"},
    )

    assert response.status_code == 401
    assert calls == []


def test_create_job_returns_created_detail(
    client,
    auth_headers,
    monkeypatch,
):
    calls = []

    class FakeRepository:
        def __init__(self, session):
            pass

        async def create(self, **kwargs):
            calls.append(kwargs)
            return make_job()

    monkeypatch.setattr(jobs_router, "JobRepository", FakeRepository)

    response = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={
            "job_description": "  负责 FastAPI 服务开发  ",
            "title": "  Python 后端开发  ",
            "company_name": "  示例科技  ",
            "extracted_requirements": {
                "responsibilities": ["负责 FastAPI 服务开发"],
                "required_skills": ["熟悉 Python"],
                "nice_to_have": [],
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["code"] == 201
    assert response.json()["data"]["job_id"] == 10
    assert calls == [
        {
            "user_id": 1,
            "raw_description": "负责 FastAPI 服务开发",
            "title": "Python 后端开发",
            "company_name": "示例科技",
            "extracted_requirements": {
                "responsibilities": ["负责 FastAPI 服务开发"],
                "required_skills": ["熟悉 Python"],
                "nice_to_have": [],
            },
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"job_description": "   "},
        {"job_description": "a" * 20_001},
        {
            "job_description": "有效描述",
            "title": "a" * 201,
        },
    ],
)
def test_create_job_validates_request(
    client,
    auth_headers,
    payload,
):
    response = client.post(
        "/api/jobs",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["code"] == 422


def test_list_jobs_returns_summaries(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeRepository:
        def __init__(self, session):
            pass

        async def list_for_user(self, user_id):
            assert user_id == 1
            return [make_job()]

    monkeypatch.setattr(jobs_router, "JobRepository", FakeRepository)

    response = client.get(
        "/api/jobs",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["job_id"] == 10
    assert data[0]["job_description_preview"].startswith(
        "负责 FastAPI"
    )
    assert data[0]["has_extracted_requirements"] is True


def test_get_job_returns_detail(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, *, job_id, user_id):
            assert job_id == 10
            assert user_id == 1
            return make_job()

    monkeypatch.setattr(jobs_router, "JobRepository", FakeRepository)

    response = client.get(
        "/api/jobs/10",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["job_description"] == (
        "负责 FastAPI 服务开发，要求熟悉 Python。"
    )


def test_get_job_returns_404_when_not_owned(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, **kwargs):
            return None

    monkeypatch.setattr(jobs_router, "JobRepository", FakeRepository)

    response = client.get(
        "/api/jobs/999",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "岗位不存在或无权访问"


def test_update_job_updates_allowed_fields(
    client,
    auth_headers,
    monkeypatch,
):
    captured = {}
    job = make_job()

    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, **kwargs):
            captured["get_for_user"] = kwargs
            return job

        async def update(self, current_job, **values):
            captured["job"] = current_job
            captured["values"] = values
            for field, value in values.items():
                setattr(current_job, field, value)
            return current_job

    monkeypatch.setattr(jobs_router, "JobRepository", FakeRepository)

    response = client.patch(
        "/api/jobs/10",
        headers=auth_headers,
        json={
            "job_description": "更新后的岗位描述",
            "title": "  Python 工程师  ",
            "company_name": "  新公司  ",
            "extracted_requirements": {
                "responsibilities": ["更新职责"],
                "required_skills": ["Python"],
                "nice_to_have": [],
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "Python 工程师"
    assert response.json()["data"]["company_name"] == "新公司"
    assert captured["job"] is job
    assert captured["get_for_user"]["for_update"] is True
    assert captured["values"] == {
        "raw_description": "更新后的岗位描述",
        "title": "Python 工程师",
        "company_name": "新公司",
        "extracted_requirements": {
            "responsibilities": ["更新职责"],
            "required_skills": ["Python"],
            "nice_to_have": [],
        },
    }


def test_update_job_without_body_fields_keeps_record(
    client,
    auth_headers,
    monkeypatch,
):
    job = make_job()
    captured = {}

    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, **kwargs):
            return job

        async def update(self, current_job, **values):
            captured["values"] = values
            return current_job

    monkeypatch.setattr(jobs_router, "JobRepository", FakeRepository)

    response = client.patch(
        "/api/jobs/10",
        headers=auth_headers,
        json={},
    )

    assert response.status_code == 200
    assert captured == {}


def test_delete_job_soft_deletes_record(
    client,
    auth_headers,
    monkeypatch,
):
    job = make_job()
    captured = {}

    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, **kwargs):
            captured["get_for_user"] = kwargs
            return job

        async def soft_delete(self, current_job):
            captured["job"] = current_job
            current_job.status = "archived"
            current_job.deleted_at = datetime.now(timezone.utc)
            return current_job

    monkeypatch.setattr(jobs_router, "JobRepository", FakeRepository)

    response = client.delete(
        "/api/jobs/10",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "job_id": 10,
        "deleted": True,
    }
    assert captured["job"] is job
    assert job.status == "archived"
    assert captured["get_for_user"]["for_update"] is True


def test_delete_job_returns_404_when_not_owned(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, **kwargs):
            return None

    monkeypatch.setattr(jobs_router, "JobRepository", FakeRepository)

    response = client.delete(
        "/api/jobs/999",
        headers=auth_headers,
    )

    assert response.status_code == 404
