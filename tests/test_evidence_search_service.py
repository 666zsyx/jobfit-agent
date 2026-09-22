# 验证关键词证据检索的评分、排序和边界。

import pytest

from app.schemas.resume import ResumeSection
from app.services.evidence_search import (
    DEFAULT_MAX_EVIDENCE_PER_REQUIREMENT,
    MAX_EVIDENCE_PER_REQUIREMENT,
    search_resume_evidence,
)


def make_section(
    section_type: str,
    title: str,
    content: str,
) -> ResumeSection:
    return ResumeSection(
        section_type=section_type,
        title=title,
        content=content,
    )


def make_sections() -> list[ResumeSection]:
    return [
        make_section(
            "skills",
            "技能",
            "Python、FastAPI、Pydantic",
        ),
        make_section(
            "project_experience",
            "项目经历",
            "使用 FastAPI 开发岗位匹配服务，负责接口设计和数据处理",
        ),
        make_section(
            "education",
            "教育经历",
            "某大学 计算机科学专业",
        ),
    ]


def test_english_technical_term_match():
    result = search_resume_evidence(
        requirements=["Python"],
        sections=make_sections(),
    )

    evidence = result.matches[0].evidence

    assert len(evidence) == 1
    assert evidence[0].content == "Python、FastAPI、Pydantic"
    assert evidence[0].score == 1.0


def test_chinese_term_match():
    result = search_resume_evidence(
        requirements=["项目经验"],
        sections=make_sections(),
    )

    evidence = result.matches[0].evidence

    assert len(evidence) == 1
    assert evidence[0].section_type == "project_experience"
    assert evidence[0].score > 0


def test_mixed_chinese_english_requirement_match():
    result = search_resume_evidence(
        requirements=["熟悉 Python 和 FastAPI"],
        sections=make_sections(),
    )

    evidence = result.matches[0].evidence

    assert len(evidence) == 2
    assert evidence[0].section_type == "skills"
    assert evidence[0].score > evidence[1].score


def test_no_overlap_returns_empty_evidence():
    result = search_resume_evidence(
        requirements=["Rust"],
        sections=make_sections(),
    )

    assert result.matches[0].evidence == []



def test_weak_chinese_ngram_only_match_is_rejected():
    sections = [
        make_section(
            "project_experience",
            "项目经历",
            "使用 FastAPI 开发岗位匹配服务",
        )
    ]

    result = search_resume_evidence(
        requirements=["有 LLM 应用开发经验"],
        sections=sections,
    )

    assert result.matches[0].evidence == []


def test_strong_chinese_english_match_is_retained():
    sections = [
        make_section(
            "skills",
            "技能",
            "Python、FastAPI、Pydantic",
        )
    ]

    result = search_resume_evidence(
        requirements=["熟悉 Python"],
        sections=sections,
    )

    assert result.matches[0].evidence


def test_evidence_sorted_by_score_descending():
    sections = [
        make_section("skills", "技能", "Python"),
        make_section("project_experience", "项目", "Python FastAPI"),
    ]

    result = search_resume_evidence(
        requirements=["Python FastAPI"],
        sections=sections,
    )

    evidence = result.matches[0].evidence

    assert [item.score for item in evidence] == [1.0, 0.5]


def test_equal_scores_preserve_original_section_order():
    sections = [
        make_section("skills", "技能一", "Python"),
        make_section("other", "技能二", "Python"),
    ]

    result = search_resume_evidence(
        requirements=["Python"],
        sections=sections,
    )

    evidence = result.matches[0].evidence

    assert [item.title for item in evidence] == ["技能一", "技能二"]


def test_evidence_count_respects_limit():
    sections = [
        make_section("skills", "技能一", "Python"),
        make_section("skills", "技能二", "Python"),
        make_section("skills", "技能三", "Python"),
    ]

    result = search_resume_evidence(
        requirements=["Python"],
        sections=sections,
        max_evidence_per_requirement=2,
    )

    assert len(result.matches[0].evidence) == 2


def test_requirements_do_not_borrow_other_evidence():
    result = search_resume_evidence(
        requirements=["Python", "Rust"],
        sections=make_sections(),
    )

    assert result.matches[0].evidence
    assert result.matches[1].evidence == []


def test_content_is_preserved_exactly():
    sections = make_sections()

    result = search_resume_evidence(
        requirements=["Python"],
        sections=sections,
    )

    evidence = result.matches[0].evidence[0]

    assert evidence.content == sections[0].content


def test_empty_requirements_are_rejected():
    with pytest.raises(ValueError, match="requirements 不能为空"):
        search_resume_evidence(
            requirements=[],
            sections=make_sections(),
        )


@pytest.mark.parametrize("requirement", ["", "   ", "\n\t"])
def test_blank_requirement_is_rejected(requirement: str):
    with pytest.raises(ValueError, match="不能为空或纯空白"):
        search_resume_evidence(
            requirements=[requirement],
            sections=make_sections(),
        )


def test_empty_sections_are_rejected():
    with pytest.raises(ValueError, match="sections 不能为空"):
        search_resume_evidence(
            requirements=["Python"],
            sections=[],
        )


@pytest.mark.parametrize(
    "max_evidence",
    [0, -1, MAX_EVIDENCE_PER_REQUIREMENT + 1, True, 1.5],
)
def test_invalid_max_evidence_is_rejected(max_evidence):
    with pytest.raises(ValueError, match="max_evidence_per_requirement"):
        search_resume_evidence(
            requirements=["Python"],
            sections=make_sections(),
            max_evidence_per_requirement=max_evidence,
        )


def test_default_evidence_limit_is_three():
    sections = [
        make_section("skills", f"技能{i}", "Python")
        for i in range(5)
    ]

    result = search_resume_evidence(
        requirements=["Python"],
        sections=sections,
    )

    assert (
        len(result.matches[0].evidence)
        == DEFAULT_MAX_EVIDENCE_PER_REQUIREMENT
    )
