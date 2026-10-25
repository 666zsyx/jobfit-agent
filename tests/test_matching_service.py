# 验证三态证据评估、汇总和 Schema 约束。

import pytest
from pydantic import ValidationError

from app.schemas.evidence import (
    EvidenceItem,
    EvidenceSearchResult,
    RequirementEvidence,
)
from app.services.matching import (
    STRONG_MATCH_SCORE,
    assess_requirement_match,
    merge_similar_assessments,
)


def make_evidence(
    score: float,
    content: str = "Python、FastAPI、Pydantic",
) -> EvidenceItem:
    return EvidenceItem(
        section_type="skills",
        title="技能",
        content=content,
        score=score,
    )


def make_search_result(
    rows: list[tuple[str, list[EvidenceItem]]],
) -> EvidenceSearchResult:
    return EvidenceSearchResult(
        requirements=[
            requirement
            for requirement, _ in rows
        ],
        matches=[
            RequirementEvidence(
                requirement=requirement,
                evidence=evidence,
            )
            for requirement, evidence in rows
        ],
    )


def test_no_evidence_returns_insufficient_evidence():
    search_result = make_search_result(
        [("有 LLM 应用开发经验", [])]
    )

    result = assess_requirement_match(search_result)

    assessment = result.assessments[0]

    assert assessment.status == "insufficient_evidence"
    assert assessment.evidence == []


def test_low_score_evidence_returns_partial_match():
    search_result = make_search_result(
        [("熟悉 Python", [make_evidence(0.5)])]
    )

    result = assess_requirement_match(search_result)

    assert result.assessments[0].status == "partial_match"


def test_score_at_threshold_returns_strong_match():
    search_result = make_search_result(
        [("熟悉 Python", [make_evidence(STRONG_MATCH_SCORE)])]
    )

    result = assess_requirement_match(search_result)

    assert result.assessments[0].status == "strong_match"


def test_multiple_evidence_uses_highest_score():
    search_result = make_search_result(
        [
            (
                "熟悉 Python",
                [
                    make_evidence(0.3, "Python"),
                    make_evidence(0.8, "Python、FastAPI"),
                ],
            )
        ]
    )

    result = assess_requirement_match(search_result)

    assert result.assessments[0].status == "strong_match"
    assert len(result.assessments[0].evidence) == 2


def test_evidence_content_is_preserved():
    evidence = make_evidence(
        score=0.5,
        content="Python、FastAPI、Pydantic",
    )
    search_result = make_search_result(
        [("熟悉 Python", [evidence])]
    )

    result = assess_requirement_match(search_result)
    actual = result.assessments[0].evidence[0]

    assert actual.section_type == evidence.section_type
    assert actual.title == evidence.title
    assert actual.content == evidence.content
    assert actual.score == evidence.score


def test_assessment_order_matches_requirements():
    search_result = make_search_result(
        [
            ("熟悉 Python", [make_evidence(0.5)]),
            ("有 LLM 应用开发经验", []),
        ]
    )

    result = assess_requirement_match(search_result)

    assert [
        assessment.requirement
        for assessment in result.assessments
    ] == search_result.requirements


def test_summary_counts_match_assessment_statuses():
    search_result = make_search_result(
        [
            ("要求一", [make_evidence(0.8)]),
            ("要求二", [make_evidence(0.5)]),
            ("要求三", []),
        ]
    )

    result = assess_requirement_match(search_result)

    assert result.summary.strong_match_count == 1
    assert result.summary.partial_match_count == 1
    assert result.summary.insufficient_evidence_count == 1


def test_summary_total_equals_requirement_count():
    search_result = make_search_result(
        [
            ("要求一", [make_evidence(0.8)]),
            ("要求二", [make_evidence(0.5)]),
            ("要求三", []),
        ]
    )

    result = assess_requirement_match(search_result)

    total_count = (
        result.summary.strong_match_count
        + result.summary.partial_match_count
        + result.summary.insufficient_evidence_count
    )

    assert total_count == len(result.assessments)
    assert total_count == len(search_result.requirements)


def test_empty_matches_are_rejected():
    search_result = EvidenceSearchResult.model_construct(
        requirements=["熟悉 Python"],
        matches=[],
    )

    with pytest.raises(ValueError, match="matches 不能为空"):
        assess_requirement_match(search_result)


def test_result_does_not_contain_not_match_status():
    search_result = make_search_result(
        [
            ("要求一", [make_evidence(0.8)]),
            ("要求二", []),
        ]
    )

    result = assess_requirement_match(search_result)

    assert all(
        assessment.status
        in {
            "strong_match",
            "partial_match",
            "insufficient_evidence",
        }
        for assessment in result.assessments
    )
    assert "not_match" not in result.model_dump_json()


def test_reason_does_not_use_model_opinion_wording():
    search_result = make_search_result(
        [("熟悉 Python", [make_evidence(0.5)])]
    )

    result = assess_requirement_match(search_result)

    assert "模型认为" not in result.assessments[0].reason


def test_invalid_summary_is_rejected():
    search_result = make_search_result(
        [("熟悉 Python", [make_evidence(0.8)])]
    )

    with pytest.raises(ValidationError):
        type(
            assess_requirement_match(search_result)
        ).model_validate(
            {
                "assessments": [
                    {
                        "requirement": "熟悉 Python",
                        "status": "strong_match",
                        "reason": "有强证据",
                        "evidence": [],
                    }
                ],
                "summary": {
                    "strong_match_count": 0,
                    "partial_match_count": 0,
                    "insufficient_evidence_count": 1,
                },
            }
        )


def test_non_evidence_search_result_is_rejected():
    with pytest.raises(
        ValueError,
        match="search_result 必须是 EvidenceSearchResult",
    ):
        assess_requirement_match({"matches": []})

def test_merge_similar_assessments_keeps_best_status():
    search_result = make_search_result(
        [
            (
                "具备 Docker 和 docker-compose 部署经验",
                [make_evidence(0.4)],
            ),
            (
                "使用 Docker 和 docker-compose 进行部署",
                [make_evidence(0.9)],
            ),
        ]
    )

    result = assess_requirement_match(search_result)
    assert len(result.assessments) == 2

    merged = merge_similar_assessments(result)

    assert len(merged.assessments) == 1
    assert merged.assessments[0].status == "strong_match"
    assert merged.summary.strong_match_count == 1
    assert merged.summary.partial_match_count == 0
