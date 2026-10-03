# 验证 section-aware chunking 的边界、偏移、哈希和确定性。

import hashlib

import pytest

from app.schemas.resume import ResumeSection
from app.services.chunking import chunk_resume_sections


def make_section(
    content: str,
    *,
    section_type: str = "project_experience",
    title: str = "项目经历",
) -> ResumeSection:
    return ResumeSection(
        section_type=section_type,
        title=title,
        content=content,
    )


def test_short_section_becomes_one_chunk():
    section = make_section("Python、FastAPI。PostgreSQL。")

    drafts = chunk_resume_sections(
        [section],
        max_chars=100,
        overlap_chars=10,
    )

    assert len(drafts) == 1
    assert drafts[0].content == section.content
    assert drafts[0].start_offset == 0
    assert drafts[0].end_offset == len(section.content)
    assert drafts[0].position == 1


def test_content_hash_matches_chunk_content():
    section = make_section("使用 FastAPI 开发课程接口。")

    draft = chunk_resume_sections(
        [section],
        max_chars=100,
        overlap_chars=10,
    )[0]

    expected_hash = hashlib.sha256(
        draft.content.encode("utf-8")
    ).hexdigest()

    assert draft.content_hash == expected_hash


def test_sections_are_not_merged():
    sections = [
        make_section("技能一。", section_type="skills", title="技能"),
        make_section(
            "项目一。",
            section_type="project_experience",
            title="项目",
        ),
    ]

    drafts = chunk_resume_sections(sections)

    assert len(drafts) == 2
    assert [draft.section_type for draft in drafts] == [
        "skills",
        "project_experience",
    ]
    assert [draft.position for draft in drafts] == [1, 2]


def test_long_section_is_split_with_overlap():
    content = "a" * 1300
    section = make_section(content)

    drafts = chunk_resume_sections(
        [section],
        max_chars=500,
        overlap_chars=50,
    )

    assert len(drafts) == 3
    assert [draft.start_offset for draft in drafts] == [0, 450, 900]
    assert [draft.end_offset for draft in drafts] == [500, 950, 1300]
    assert all(len(draft.content) <= 500 for draft in drafts)


def test_offsets_can_reconstruct_original_content():
    content = "第一句。" * 200
    section = make_section(content)

    drafts = chunk_resume_sections(
        [section],
        max_chars=300,
        overlap_chars=40,
    )

    for draft in drafts:
        expected = content[
            draft.start_offset:draft.end_offset
        ]
        assert draft.content == expected


def test_chunking_is_deterministic():
    section = make_section("需求评审。接口开发。联调上线。" * 50)

    first = chunk_resume_sections(
        [section],
        max_chars=250,
        overlap_chars=30,
    )
    second = chunk_resume_sections(
        [section],
        max_chars=250,
        overlap_chars=30,
    )

    assert first == second


def test_empty_sections_are_rejected():
    with pytest.raises(ValueError, match="sections 不能为空"):
        chunk_resume_sections([])


def test_overlap_must_be_smaller_than_max_chars():
    section = make_section("Python、FastAPI。")

    with pytest.raises(ValueError, match="overlap_chars 必须小于"):
        chunk_resume_sections(
            [section],
            max_chars=100,
            overlap_chars=100,
        )
