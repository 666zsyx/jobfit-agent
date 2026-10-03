# 验证简历上传、列表和详情接口。

from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers import resumes as resumes_router
from app.services.resume_ingestion import (
    ResumeExtractionOutcome,
    ResumeIngestionResult,
)


def make_version(resume_version_id: int = 20) -> SimpleNamespace:
    return SimpleNamespace(
        resume_version_id=resume_version_id,
        version_no=1,
        source_type="txt",
        raw_text="Python 后端开发经验",
        extracted_sections=None,
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

    async def fake_extract_resume_sections(resume_text):
        return ResumeExtractionOutcome(
            status="completed",
            extracted_sections={"sections": [{"title": "技能"}]},
            total_tokens=30,
        )

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
        captured["extracted_sections"] = extracted_sections
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
        "extract_resume_sections_safely",
        fake_extract_resume_sections,
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
    assert data["extraction_status"] == "completed"
    assert captured["parsed"].text == "Python 后端开发经验"
    assert captured["extracted_sections"] == {
        "sections": [{"title": "技能"}]
    }
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

def test_upload_resume_keeps_raw_text_when_extraction_fails(
    client,
    auth_headers,
    monkeypatch,
):
    captured = {}

    async def fake_extract_resume_sections(resume_text):
        return ResumeExtractionOutcome(
            status="failed",
            error_code="llm_service_error",
            total_tokens=20,
        )

    async def fake_persist_parsed_resume(
        session,
        *,
        user_id,
        parsed,
        resume_id=None,
        title=None,
        extracted_sections=None,
    ):
        captured["parsed"] = parsed
        captured["extracted_sections"] = extracted_sections
        return ResumeIngestionResult(
            resume_id=11,
            resume_version_id=21,
            version_no=1,
            title=title or "上传简历",
            source_type=parsed.source_type,
            char_count=parsed.char_count,
        )

    monkeypatch.setattr(
        resumes_router,
        "extract_resume_sections_safely",
        fake_extract_resume_sections,
    )
    monkeypatch.setattr(
        resumes_router,
        "persist_parsed_resume",
        fake_persist_parsed_resume,
    )

    response = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        files={
            "file": (
                "resume.txt",
                "Python 后端开发经验".encode("utf-8"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["extraction_status"] == "failed"
    assert captured["extracted_sections"] is None
    assert captured["parsed"].text == "Python 后端开发经验"


def test_upload_resume_can_skip_structured_extraction(
    client,
    auth_headers,
    monkeypatch,
):
    async def fail_if_called(resume_text):
        raise AssertionError("不应调用结构提取")

    async def fake_persist_parsed_resume(
        session,
        *,
        user_id,
        parsed,
        resume_id=None,
        title=None,
        extracted_sections=None,
    ):
        return ResumeIngestionResult(
            resume_id=12,
            resume_version_id=22,
            version_no=1,
            title=title or "上传简历",
            source_type=parsed.source_type,
            char_count=parsed.char_count,
        )

    monkeypatch.setattr(
        resumes_router,
        "extract_resume_sections_safely",
        fail_if_called,
    )
    monkeypatch.setattr(
        resumes_router,
        "persist_parsed_resume",
        fake_persist_parsed_resume,
    )

    response = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        data={"extract_sections": "false"},
        files={
            "file": (
                "resume.txt",
                "Python 后端开发经验".encode("utf-8"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["extraction_status"] == "skipped"


def test_retry_resume_extraction_updates_version(
    client,
    auth_headers,
    monkeypatch,
):
    version = SimpleNamespace(
        resume_id=10,
        resume_version_id=20,
        source_type="txt",
        raw_text="Python 后端开发经验",
        extracted_sections=None,
    )

    class FakeVersionRepository:
        def __init__(self, session):
            pass

        async def get_for_user(self, **kwargs):
            assert kwargs["resume_version_id"] == 20
            assert kwargs["user_id"] == 1
            return version

    async def fake_extract_resume_sections(resume_text):
        return ResumeExtractionOutcome(
            status="completed",
            extracted_sections={"sections": [{"title": "技能"}]},
            total_tokens=15,
        )

    monkeypatch.setattr(
        resumes_router,
        "ResumeVersionRepository",
        FakeVersionRepository,
    )
    monkeypatch.setattr(
        resumes_router,
        "extract_resume_sections_safely",
        fake_extract_resume_sections,
    )

    response = client.post(
        "/api/resumes/10/versions/20/extract",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["extraction_status"] == "completed"
    assert response.json()["data"]["has_extracted_sections"] is True
    assert version.extracted_sections == {
        "sections": [{"title": "技能"}]
    }
