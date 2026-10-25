# 计算 Agent 评估指标并聚合固定评估集。

from __future__ import annotations

import math
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MatchStatus = Literal[
    "strong_match",
    "partial_match",
    "insufficient_evidence",
]


class ExpectedAgentOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_status: str = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    match_statuses: list[MatchStatus] = Field(default_factory=list)
    citation_ids: list[int] = Field(default_factory=list)
    should_abstain: bool = False
    requires_confirmation: bool = False
    # Expected tool errors (fault injection / recovery cases).
    expected_tool_error_count: int = Field(default=0, ge=0)


class ObservedAgentOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_status: str = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    match_statuses: list[MatchStatus] = Field(default_factory=list)
    citation_ids: list[int] = Field(default_factory=list)
    abstained: bool = False
    confirmation_recovered: bool = False
    tool_call_count: int = Field(ge=0)
    tool_error_count: int = Field(ge=0)
    suggestion_count: int = Field(ge=0)
    unsupported_suggestion_count: int = Field(ge=0)
    steps: int = Field(ge=0)
    usage_total: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_counts(self):
        if self.tool_error_count > self.tool_call_count:
            raise ValueError("tool_error_count 不能大于 tool_call_count")
        if self.unsupported_suggestion_count > self.suggestion_count:
            raise ValueError(
                "unsupported_suggestion_count 不能大于 suggestion_count"
            )
        return self


class AgentEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    job_description: str = Field(min_length=1)
    resume_text: str = Field(min_length=1)
    expected: ExpectedAgentOutcome
    observed: ObservedAgentOutcome


class AgentCaseMetrics(BaseModel):
    task_completed: bool
    # 严格全等：工具名、顺序、数量都必须与期望完全一致。
    tool_sequence_accuracy: float = Field(ge=0, le=1)
    tool_precision: float = Field(ge=0, le=1)
    # 必要工具覆盖率：期望工具被真实调用的比例，容忍多调用的额外工具。
    tool_recall: float = Field(ge=0, le=1)
    tool_f1: float = Field(ge=0, le=1)
    tool_success_rate: float = Field(ge=0, le=1)
    match_status_f1: float = Field(ge=0, le=1)
    citation_precision: float = Field(ge=0, le=1)
    citation_recall: float = Field(ge=0, le=1)
    citation_f1: float = Field(ge=0, le=1)
    citation_valid: bool
    abstention_correct: bool
    confirmation_recovered: bool
    unsupported_suggestion_rate: float = Field(ge=0, le=1)


class AgentCaseResult(BaseModel):
    case_id: str
    category: str
    metrics: AgentCaseMetrics
    observed_error_code: str | None = None


class AgentEvaluationSummary(BaseModel):
    case_count: int = Field(ge=1)
    task_completion_rate: float = Field(ge=0, le=1)
    tool_sequence_accuracy: float = Field(ge=0, le=1)
    tool_precision: float = Field(ge=0, le=1)
    tool_recall: float = Field(ge=0, le=1)
    tool_f1: float = Field(ge=0, le=1)
    tool_success_rate: float = Field(ge=0, le=1)
    match_status_f1: float = Field(ge=0, le=1)
    citation_f1: float = Field(ge=0, le=1)
    citation_validity_rate: float = Field(ge=0, le=1)
    abstention_accuracy: float = Field(ge=0, le=1)
    confirmation_recovery_rate: float = Field(ge=0, le=1)
    unsupported_suggestion_rate: float = Field(ge=0, le=1)
    average_steps: float = Field(ge=0)
    average_usage_total: float = Field(ge=0)
    p50_latency_ms: float = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)


def _prf1(
    expected: list[str],
    observed: list[str],
) -> tuple[float, float, float]:
    if not expected and not observed:
        return 1.0, 1.0, 1.0

    expected_counts = Counter(expected)
    observed_counts = Counter(observed)
    overlap = sum(
        min(expected_counts[label], observed_counts[label])
        for label in expected_counts.keys() | observed_counts.keys()
    )
    precision = overlap / len(observed) if observed else 0.0
    recall = overlap / len(expected) if expected else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall > 0
        else 0.0
    )
    return precision, recall, f1


def _numeric_prf1(
    expected: list[int],
    observed: list[int],
) -> tuple[float, float, float]:
    return _prf1(
        [str(value) for value in expected],
        [str(value) for value in observed],
    )


def _percentile(values: list[int | float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * ratio) - 1)
    return float(ordered[index])


def evaluate_agent_case(case: AgentEvaluationCase) -> AgentCaseResult:
    expected = case.expected
    observed = case.observed

    tool_precision, tool_recall, tool_f1 = _prf1(
        expected.tools,
        observed.tools,
    )
    _, _, match_status_f1 = _prf1(
        expected.match_statuses,
        observed.match_statuses,
    )
    citation_precision, citation_recall, citation_f1 = _numeric_prf1(
        expected.citation_ids,
        observed.citation_ids,
    )
    expected_citations = set(expected.citation_ids)
    observed_citations = set(observed.citation_ids)

    if expected.task_status != "completed":
        citation_valid = True
    elif expected.should_abstain:
        citation_valid = not observed_citations
    else:
        citation_valid = (
            bool(observed_citations)
            and observed_citations == expected_citations
            and len(observed.citation_ids) == len(expected.citation_ids)
        )

    unexpected_tool_error_count = max(
        0,
        observed.tool_error_count - expected.expected_tool_error_count,
    )
    tool_success_rate = (
        1.0
        if observed.tool_call_count == 0
        else 1.0
        - (unexpected_tool_error_count / observed.tool_call_count)
    )
    unsupported_suggestion_rate = (
        0.0
        if observed.suggestion_count == 0
        else observed.unsupported_suggestion_count / observed.suggestion_count
    )

    metrics = AgentCaseMetrics(
        task_completed=observed.task_status == expected.task_status,
        # 严格全等：多调一个工具就会被判为 0。
        tool_sequence_accuracy=(
            1.0 if observed.tools == expected.tools else 0.0
        ),
        tool_precision=tool_precision,
        tool_recall=tool_recall,
        tool_f1=tool_f1,
        tool_success_rate=tool_success_rate,
        match_status_f1=match_status_f1,
        citation_precision=citation_precision,
        citation_recall=citation_recall,
        citation_f1=citation_f1,
        citation_valid=citation_valid,
        abstention_correct=observed.abstained == expected.should_abstain,
        confirmation_recovered=(
            observed.confirmation_recovered
            if expected.requires_confirmation
            else True
        ),
        unsupported_suggestion_rate=unsupported_suggestion_rate,
    )
    return AgentCaseResult(
        case_id=case.case_id,
        category=case.category,
        metrics=metrics,
        observed_error_code=observed.error_code,
    )


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def summarize_agent_results(
    results: list[AgentCaseResult],
    *,
    observed_outcomes: list[ObservedAgentOutcome] | None = None,
) -> AgentEvaluationSummary:
    if not results:
        raise ValueError("results 不能为空")

    metrics = [result.metrics for result in results]
    outcomes = observed_outcomes or []
    confirmation_metrics = [
        metric.confirmation_recovered
        for metric in metrics
    ]

    return AgentEvaluationSummary(
        case_count=len(results),
        task_completion_rate=_mean(
            [1.0 if metric.task_completed else 0.0 for metric in metrics]
        ),
        tool_sequence_accuracy=_mean(
            [metric.tool_sequence_accuracy for metric in metrics]
        ),
        tool_precision=_mean(
            [metric.tool_precision for metric in metrics]
        ),
        tool_recall=_mean([metric.tool_recall for metric in metrics]),
        tool_f1=_mean([metric.tool_f1 for metric in metrics]),
        tool_success_rate=_mean(
            [metric.tool_success_rate for metric in metrics]
        ),
        match_status_f1=_mean(
            [metric.match_status_f1 for metric in metrics]
        ),
        citation_f1=_mean([metric.citation_f1 for metric in metrics]),
        citation_validity_rate=_mean(
            [1.0 if metric.citation_valid else 0.0 for metric in metrics]
        ),
        abstention_accuracy=_mean(
            [1.0 if metric.abstention_correct else 0.0 for metric in metrics]
        ),
        confirmation_recovery_rate=_mean(
            [1.0 if value else 0.0 for value in confirmation_metrics]
        ),
        unsupported_suggestion_rate=_mean(
            [metric.unsupported_suggestion_rate for metric in metrics]
        ),
        average_steps=_mean(
            [float(outcome.steps) for outcome in outcomes]
        ),
        average_usage_total=_mean(
            [float(outcome.usage_total) for outcome in outcomes]
        ),
        p50_latency_ms=_percentile(
            [outcome.latency_ms for outcome in outcomes],
            0.50,
        ),
        p95_latency_ms=_percentile(
            [outcome.latency_ms for outcome in outcomes],
            0.95,
        ),
    )


__all__ = [
    "AgentCaseMetrics",
    "AgentCaseResult",
    "AgentEvaluationCase",
    "AgentEvaluationSummary",
    "ExpectedAgentOutcome",
    "ObservedAgentOutcome",
    "evaluate_agent_case",
    "summarize_agent_results",
]
