# 根据检索证据评估要求的证据充分性。

from app.schemas.evidence import (
    EvidenceSearchResult,
    RequirementEvidence,
)
from app.schemas.matching import (
    MatchAssessmentResult,
    MatchSummary,
    RequirementAssessment,
)
from app.services.text_similarity import requirements_are_similar

STRONG_MATCH_SCORE = 0.6


# 根据单条要求是否存在证据及其最高分决定三态结果。
def _assess_one_requirement(
    match: RequirementEvidence,
) -> RequirementAssessment:
    if not match.evidence:
        return RequirementAssessment(
            requirement=match.requirement,
            status="insufficient_evidence",
            reason="未检索到相关的简历原文证据。",
            evidence=[],
        )

    max_score = max(item.score for item in match.evidence)

    if max_score >= STRONG_MATCH_SCORE:
        return RequirementAssessment(
            requirement=match.requirement,
            status="strong_match",
            reason=(
                f"存在最高分为 {max_score:.3f} 的原文证据，"
                f"达到强匹配阈值 {STRONG_MATCH_SCORE:.1f}。"
            ),
            evidence=match.evidence,
        )

    return RequirementAssessment(
        requirement=match.requirement,
        status="partial_match",
        reason=(
            f"存在最高分为 {max_score:.3f} 的原文证据，"
            f"但未达到强匹配阈值 {STRONG_MATCH_SCORE:.1f}。"
        ),
        evidence=match.evidence,
    )


# 评估全部岗位要求，并生成状态汇总。
def assess_requirement_match(
    search_result: EvidenceSearchResult,
) -> MatchAssessmentResult:
    if not isinstance(search_result, EvidenceSearchResult):
        raise ValueError(  # noqa: TRY004
            "search_result 必须是 EvidenceSearchResult"
        )

    if not search_result.matches:
        raise ValueError("matches 不能为空")

    assessments = [
        _assess_one_requirement(match)
        for match in search_result.matches
    ]

    strong_match_count = sum(
        assessment.status == "strong_match"
        for assessment in assessments
    )
    partial_match_count = sum(
        assessment.status == "partial_match"
        for assessment in assessments
    )
    insufficient_evidence_count = sum(
        assessment.status == "insufficient_evidence"
        for assessment in assessments
    )

    return MatchAssessmentResult(
        assessments=assessments,
        summary=MatchSummary(
            strong_match_count=strong_match_count,
            partial_match_count=partial_match_count,
            insufficient_evidence_count=insufficient_evidence_count,
        ),
    )

_STATUS_RANK = {
    "insufficient_evidence": 0,
    "partial_match": 1,
    "strong_match": 2,
}


def _best_assessment(
    assessments: list[RequirementAssessment],
) -> RequirementAssessment:
    return max(
        assessments,
        key=lambda assessment: (
            _STATUS_RANK[assessment.status],
            max(
                (item.score for item in assessment.evidence),
                default=-1.0,
            ),
            len(assessment.evidence),
        ),
    )


def merge_similar_assessments(
    result: MatchAssessmentResult,
) -> MatchAssessmentResult:
    merged: list[RequirementAssessment] = []
    for assessment in result.assessments:
        duplicate_index = None
        for index, existing in enumerate(merged):
            if requirements_are_similar(
                assessment.requirement,
                existing.requirement,
            ):
                duplicate_index = index
                break
        if duplicate_index is None:
            merged.append(assessment)
        else:
            merged[duplicate_index] = _best_assessment(
                [merged[duplicate_index], assessment]
            )

    strong_match_count = sum(
        assessment.status == "strong_match"
        for assessment in merged
    )
    partial_match_count = sum(
        assessment.status == "partial_match"
        for assessment in merged
    )
    insufficient_evidence_count = sum(
        assessment.status == "insufficient_evidence"
        for assessment in merged
    )

    return MatchAssessmentResult(
        assessments=merged,
        summary=MatchSummary(
            strong_match_count=strong_match_count,
            partial_match_count=partial_match_count,
            insufficient_evidence_count=insufficient_evidence_count,
        ),
    )
