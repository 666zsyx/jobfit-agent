# 验证 Agent 评估指标和固定评估集。

import json
from pathlib import Path

import pytest

from app.services.agent_evaluation import (
    AgentEvaluationCase,
    evaluate_agent_case,
    summarize_agent_results,
)

DATASET_PATH = Path(__file__).resolve().parents[1] / (
    "data/evaluation/agent_cases.json"
)


def make_case(**overrides) -> AgentEvaluationCase:
    data = {
        "case_id": "case-1",
        "category": "test",
        "job_description": "需要 Python。",
        "resume_text": "使用 Python。",
        "expected": {
            "task_status": "completed",
            "tools": ["extract_job_requirements", "save_match_report"],
            "match_statuses": ["strong_match"],
            "citation_ids": [1],
            "should_abstain": False,
            "requires_confirmation": True,
        },
        "observed": {
            "task_status": "completed",
            "tools": ["extract_job_requirements", "save_match_report"],
            "match_statuses": ["strong_match"],
            "citation_ids": [1],
            "abstained": False,
            "confirmation_recovered": True,
            "tool_call_count": 2,
            "tool_error_count": 0,
            "suggestion_count": 1,
            "unsupported_suggestion_count": 0,
            "steps": 2,
            "usage_total": 100,
            "latency_ms": 10,
            "error_code": None,
        },
    }
    for key, value in overrides.items():
        if key in {"expected", "observed"}:
            data[key].update(value)
        else:
            data[key] = value
    return AgentEvaluationCase.model_validate(data)


def test_perfect_case_has_perfect_metrics() -> None:
    result = evaluate_agent_case(make_case())

    assert result.metrics.task_completed is True
    assert result.metrics.tool_f1 == 1.0
    assert result.metrics.citation_f1 == 1.0
    assert result.metrics.citation_valid is True
    assert result.metrics.unsupported_suggestion_rate == 0.0


def test_missing_citation_reduces_citation_recall() -> None:
    result = evaluate_agent_case(
        make_case(
            expected={"citation_ids": [1, 2]},
            observed={"citation_ids": [1]},
        )
    )

    assert result.metrics.citation_recall == 0.5
    assert result.metrics.citation_f1 == pytest.approx(2 / 3)
    assert result.metrics.citation_valid is False


def test_unknown_citation_is_invalid() -> None:
    result = evaluate_agent_case(
        make_case(
            expected={"citation_ids": [1]},
            observed={"citation_ids": [2]},
        )
    )

    assert result.metrics.citation_valid is False


def test_duplicate_citation_is_invalid() -> None:
    result = evaluate_agent_case(
        make_case(
            expected={"citation_ids": [1]},
            observed={"citation_ids": [1, 1]},
        )
    )

    assert result.metrics.citation_valid is False


def test_citation_valid_override_is_used() -> None:
    result = evaluate_agent_case(
        make_case(
            expected={"citation_ids": [1]},
            observed={
                "citation_ids": [999],
                "citation_ids_valid": True,
            },
        )
    )

    assert result.metrics.citation_valid is True


def test_abstention_case_requires_empty_citations() -> None:
    result = evaluate_agent_case(
        make_case(
            expected={
                "should_abstain": True,
                "citation_ids": [],
                "match_statuses": ["insufficient_evidence"],
            },
            observed={
                "abstained": True,
                "citation_ids": [],
                "match_statuses": ["insufficient_evidence"],
            },
        )
    )

    assert result.metrics.abstention_correct is True
    assert result.metrics.citation_valid is True


def test_unsupported_suggestion_rate_is_detected() -> None:
    result = evaluate_agent_case(
        make_case(
            observed={
                "suggestion_count": 4,
                "unsupported_suggestion_count": 2,
            }
        )
    )

    assert result.metrics.unsupported_suggestion_rate == 0.5


def test_expected_tool_error_count_does_not_reduce_success_rate() -> None:
    result = evaluate_agent_case(
        make_case(
            expected={"expected_tool_error_count": 1},
            observed={
                "tool_call_count": 3,
                "tool_error_count": 1,
            },
        )
    )

    assert result.metrics.tool_success_rate == 1.0


def test_tool_sequence_accuracy_is_strict() -> None:
    result = evaluate_agent_case(
        make_case(
            expected={"tools": ["a", "b"]},
            observed={"tools": ["a", "x", "b"]},
        )
    )

    assert result.metrics.tool_sequence_accuracy == 0.0
    assert result.metrics.tool_f1 < 1.0


def test_fixed_dataset_is_valid_and_summarizable() -> None:
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    cases = [
        AgentEvaluationCase.model_validate(item)
        for item in payload["cases"]
    ]

    assert len(cases) == 50
    assert len({case.case_id for case in cases}) == len(cases)

    results = [evaluate_agent_case(case) for case in cases]
    summary = summarize_agent_results(
        results,
        observed_outcomes=[case.observed for case in cases],
    )

    assert summary.case_count == 50
    assert 0 <= summary.task_completion_rate <= 1
    assert 0 <= summary.tool_f1 <= 1
    assert 0 <= summary.citation_f1 <= 1
    assert 0 <= summary.unsupported_suggestion_rate <= 1

def test_interrupted_case_does_not_require_citation() -> None:
    result = evaluate_agent_case(
        make_case(
            expected={
                "task_status": "interrupted",
                "citation_ids": [],
            },
            observed={
                "task_status": "interrupted",
                "citation_ids": [],
            },
        )
    )

    assert result.metrics.task_completed is True
    assert result.metrics.citation_valid is True


def test_summary_exposes_tool_precision_and_recall() -> None:
    case = make_case()
    result = evaluate_agent_case(case)
    summary = summarize_agent_results(
        [result],
        observed_outcomes=[case.observed],
    )

    assert summary.tool_precision == 1.0
    assert summary.tool_recall == 1.0


def test_extra_tool_only_reduces_precision_not_recall() -> None:
    case = make_case(
        expected={"tools": ["a", "b"]},
        observed={"tools": ["a", "x", "b"]},
    )
    result = evaluate_agent_case(case)
    summary = summarize_agent_results(
        [result],
        observed_outcomes=[case.observed],
    )

    # 严格全等为 0，但必要工具都调到了。
    assert summary.tool_sequence_accuracy == 0.0
    assert summary.tool_recall == 1.0
    assert summary.tool_precision < 1.0
