# 验证简历上传、列表和详情接口。

from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers import resumes as resumes_router
from app.services.resume_ingestion import ResumeIngestionResult


def make_version(resume_version_id: int = 20) -> SimpleNamespace:
    return SimpleNamespace(
        resume_version_id=resume_version_id,
        version_no=1,
        source_type="txt",
        raw_text="Python 后端开发经验",
        created_at=datetime.now(timezone.utc),
    )


def make_resume() -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        resume_id=10,
        title="测试简历",
        status="active",
        created_at=now,
        updated_at=now,
        versions=[make_version()],
    )


def test_upload_resume_txt_returns_version(
    client,
    auth_headers,
    monkeypatch,
):
    captured = {}

    async def fake_persist_parsed_resume(
        session,
        *,
        user_id,
        parsed,
        resume_id=None,
        title=None,
        extracted_sections=None,
    ):
        captured["user_id"] = user_id
        captured["parsed"] = parsed
        captured["resume_id"] = resume_id
        captured["title"] = title
        return ResumeIngestionResult(
            resume_id=10,
            resume_version_id=20,
            version_no=1,
            title=title or "上传简历",
            source_type=parsed.source_type,
            char_count=parsed.char_count,
        )

    monkeypatch.setattr(
        resumes_router,
        "persist_parsed_resume",
        fake_persist_parsed_resume,
    )

    response = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        data={"title": "测试简历"},
        files={
            "file": (
                "resume.txt",
                "Python 后端开发经验".encode("utf-8"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["resume_id"] == 10
    assert data["resume_version_id"] == 20
    assert data["source_type"] == "txt"
    assert captured["parsed"].text == "Python 后端开发经验"
    assert captured["user_id"] == 1


def test_upload_resume_rejects_legacy_doc(
    client,
    auth_headers,
):
    response = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        files={
            "file": (
                "resume.doc",
                b"not a docx",
                "application/msword",
            )
        },
    )

    assert response.status_code == 415
    assert response.json()["data"]["error_code"] == "unsupported_file_type"


def test_list_resumes_returns_current_user_items(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeResumeRepository:
        def __init__(self, session):
            pass

        async def list_for_user(self, user_id, with_versions=False):
            assert user_id == 1
            assert with_versions is True
            return [make_resume()]

    monkeypatch.setattr(
        resumes_router,
        "ResumeRepository",
        FakeResumeRepository,
    )

    response = client.get(
        "/api/resumes",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["resume_id"] == 10
    assert data[0]["latest_version_no"] == 1
    assert data[0]["latest_source_type"] == "txt"


def test_get_resume_returns_versions(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeResumeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(
            self,
            resume_id,
            user_id,
            with_versions=False,
        ):
            assert resume_id == 10
            assert user_id == 1
            assert with_versions is True
            return make_resume()

    monkeypatch.setattr(
        resumes_router,
        "ResumeRepository",
        FakeResumeRepository,
    )

    response = client.get(
        "/api/resumes/10",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["resume_id"] == 10
    assert data["versions"][0]["source_type"] == "txt"


def test_get_resume_returns_404_for_other_user(
    client,
    auth_headers,
    monkeypatch,
):
    class FakeResumeRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, **kwargs):
            return None

    monkeypatch.setattr(
        resumes_router,
        "ResumeRepository",
        FakeResumeRepository,
    )

    response = client.get(
        "/api/resumes/999",
        headers=auth_headers,
    )

    assert response.status_code == 404
