# 验证解析结果保存为简历版本和用户隔离。

import asyncio
from types import SimpleNamespace

import pytest

from app.services import resume_ingestion
from app.services.resume_file_parser import ResumeParseResult
from app.services.resume_ingestion import persist_parsed_resume


def make_parsed() -> ResumeParseResult:
    return ResumeParseResult(
        text="Python 后端开发经验",
        source_type="pdf",
        original_filename="my_resume.pdf",
        page_count=1,
        char_count=12,
    )


class FakeResumeRepository:
    created: list[dict] = []
    existing: SimpleNamespace | None = None

    def __init__(self, session):
        self.session = session

    async def create(self, user_id: int, title: str):
        resume = SimpleNamespace(
            resume_id=10,
            user_id=user_id,
            title=title,
        )
        self.created.append(
            {"user_id": user_id, "title": title, "resume": resume}
        )
        return resume

    async def get_for_user(self, resume_id: int, user_id: int):
        if (
            self.existing is not None
            and self.existing.resume_id == resume_id
            and self.existing.user_id == user_id
        ):
            return self.existing
        return None


class FakeResumeVersionRepository:
    calls: list[dict] = []

    def __init__(self, session):
        self.session = session

    async def create_for_user(
        self,
        *,
        resume_id: int,
        user_id: int,
        version_no: int,
        raw_text: str,
        extracted_sections: dict | None,
        source_type: str,
    ):
        self.calls.append(
            {
                "resume_id": resume_id,
                "user_id": user_id,
                "version_no": version_no,
                "raw_text": raw_text,
                "source_type": source_type,
            }
        )
        return SimpleNamespace(
            resume_version_id=20,
            resume_id=resume_id,
            version_no=version_no,
            raw_text=raw_text,
            source_type=source_type,
        )

    async def create_next_for_user(
        self,
        *,
        resume_id: int,
        user_id: int,
        raw_text: str,
        extracted_sections: dict | None,
        source_type: str,
    ):
        self.calls.append(
            {
                "resume_id": resume_id,
                "user_id": user_id,
                "version_no": 2,
                "raw_text": raw_text,
                "source_type": source_type,
            }
        )
        return SimpleNamespace(
            resume_version_id=21,
            resume_id=resume_id,
            version_no=2,
            raw_text=raw_text,
            source_type=source_type,
        )


def test_create_new_resume_and_first_version(monkeypatch) -> None:
    FakeResumeRepository.created = []
    FakeResumeVersionRepository.calls = []
    FakeResumeRepository.existing = None
    monkeypatch.setattr(
        resume_ingestion,
        "ResumeRepository",
        FakeResumeRepository,
    )
    monkeypatch.setattr(
        resume_ingestion,
        "ResumeVersionRepository",
        FakeResumeVersionRepository,
    )

    result = asyncio.run(
        persist_parsed_resume(
            object(),
            user_id=7,
            parsed=make_parsed(),
        )
    )

    assert result.resume_id == 10
    assert result.resume_version_id == 20
    assert result.version_no == 1
    assert result.title == "my_resume"
    assert FakeResumeVersionRepository.calls[0]["source_type"] == "pdf"


def test_append_new_version_to_owned_resume(monkeypatch) -> None:
    FakeResumeRepository.created = []
    FakeResumeVersionRepository.calls = []
    FakeResumeRepository.existing = SimpleNamespace(
        resume_id=10,
        user_id=7,
        title="现有简历",
    )
    monkeypatch.setattr(
        resume_ingestion,
        "ResumeRepository",
        FakeResumeRepository,
    )
    monkeypatch.setattr(
        resume_ingestion,
        "ResumeVersionRepository",
        FakeResumeVersionRepository,
    )

    result = asyncio.run(
        persist_parsed_resume(
            object(),
            user_id=7,
            resume_id=10,
            parsed=make_parsed(),
        )
    )

    assert result.version_no == 2
    assert result.resume_version_id == 21
    assert FakeResumeRepository.created == []


def test_append_rejects_other_user_resume(monkeypatch) -> None:
    FakeResumeRepository.created = []
    FakeResumeVersionRepository.calls = []

    class RejectingVersionRepository(FakeResumeVersionRepository):
        async def create_next_for_user(self, **kwargs):
            raise LookupError("简历不存在或无权访问")

    FakeResumeRepository.existing = None
    monkeypatch.setattr(
        resume_ingestion,
        "ResumeRepository",
        FakeResumeRepository,
    )
    monkeypatch.setattr(
        resume_ingestion,
        "ResumeVersionRepository",
        RejectingVersionRepository,
    )

    with pytest.raises(LookupError):
        asyncio.run(
            persist_parsed_resume(
                object(),
                user_id=7,
                resume_id=999,
                parsed=make_parsed(),
            )
        )
