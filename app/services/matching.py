# 根据检索证据评估要求的证据充分性。

import re

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


_NEGATION_WORDS = (
    "没有",
    "未",
    "没",
    "不熟悉",
    "不掌握",
    "缺乏",
    "未做过",
    "没做过",
    "未参与",
    "未实现",
    "没实现",
)
_WEAK_SCOPE_WORDS = (
    "简单",
    "小规模",
    "本地",
    "内部",
    "demo",
    "测试集群",
    "未参与生产",
    "未参与大型",
    "只做过",
    "仅",
    "基础",
    "了解",
)
_STRONG_SCOPE_WORDS = (
    "复杂",
    "分布式",
    "高并发",
    "大型",
    "生产",
    "故障",
    "人工确认",
    "断点恢复",
    "集群运维",
    "分库分表",
)
_ASCII_TERM_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9.+#-]*")
_CLAUSE_SEPARATORS = "，,。；;：:、"
_ENGLISH_STOPWORDS = {
    "and",
    "or",
    "the",
    "with",
    "for",
    "experience",
    "skill",
    "skills",
    "development",
    "developer",
    "backend",
    "frontend",
}


def _ascii_terms(text: str) -> list[str]:
    return [
        term
        for term in _ASCII_TERM_PATTERN.findall(text)
        if len(term) >= 2 and term.lower() not in _ENGLISH_STOPWORDS
    ]


def _term_spans(content: str, term: str) -> list[tuple[int, int]]:
    if term.isascii():
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        return [
            (match.start(), match.end())
            for match in pattern.finditer(content)
        ]

    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        index = content.find(term, start)
        if index < 0:
            break
        spans.append((index, index + len(term)))
        start = index + len(term)
    return spans


def _clause_text(content: str, start: int, end: int) -> str:
    left = -1
    for separator in _CLAUSE_SEPARATORS:
        left = max(left, content.rfind(separator, 0, start))

    right = len(content)
    for separator in _CLAUSE_SEPARATORS:
        index = content.find(separator, end)
        if index != -1:
            right = min(right, index)
    return content[left + 1:right]


def _has_negation_near_term(content: str, term: str) -> bool:
    for start, end in _term_spans(content, term):
        clause = _clause_text(content, start, end)
        if any(word in clause for word in _NEGATION_WORDS):
            return True
    return False


def _evidence_is_negative(requirement: str, content: str) -> bool:
    terms = _ascii_terms(requirement)
    return any(
        _has_negation_near_term(content, term)
        for term in terms
    )


def _scope_is_limited(requirement: str, evidence_items) -> bool:
    for item in evidence_items:
        if any(word in item.content for word in _WEAK_SCOPE_WORDS):
            return True
        for word in _STRONG_SCOPE_WORDS:
            if word in requirement and _has_negation_near_term(
                item.content,
                word,
            ):
                return True
    return False


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

    positive_evidence = [
        item
        for item in match.evidence
        if not _evidence_is_negative(match.requirement, item.content)
    ]
    if not positive_evidence:
        return RequirementAssessment(
            requirement=match.requirement,
            status="insufficient_evidence",
            reason="检索到的证据是否定表述，不能作为匹配依据。",
            evidence=[],
        )

    if _scope_is_limited(match.requirement, positive_evidence):
        return RequirementAssessment(
            requirement=match.requirement,
            status="partial_match",
            reason="证据只覆盖基础场景，未达到要求的范围或深度。",
            evidence=positive_evidence,
        )

    max_score = max(item.score for item in positive_evidence)

    if max_score >= STRONG_MATCH_SCORE:
        return RequirementAssessment(
            requirement=match.requirement,
            status="strong_match",
            reason=(
                f"存在最高分为 {max_score:.3f} 的原文证据，"
                f"达到强匹配阈值 {STRONG_MATCH_SCORE:.1f}。"
            ),
            evidence=positive_evidence,
        )

    return RequirementAssessment(
        requirement=match.requirement,
        status="partial_match",
        reason=(
            f"存在最高分为 {max_score:.3f} 的原文证据，"
            f"但未达到强匹配阈值 {STRONG_MATCH_SCORE:.1f}。"
        ),
        evidence=positive_evidence,
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
