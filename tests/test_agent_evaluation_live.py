# 验证真实执行评估脚本的观测值推导和评分复用。

import json

from app.schemas.chat import TokenUsage
from app.schemas.react_agent import ReactAgentResult, ReactToolExecution
from scripts.evaluate_agent_live import (
    derive_observed_outcome,
    load_dataset,
    score_live_observations,
    skip_reason,
)


def make_execution(name, result, *, step=1, call_id="call-1"):
    return ReactToolExecution(
        step=step,
        tool_call_id=call_id,
        tool_name=name,
        arguments={},
        result=result,
    )


def make_result(trace, *, status="completed", steps=3, tokens=1200):
    return ReactAgentResult(
        answer="分析完成" if status == "completed" else None,
        status=status,
        steps=steps,
        max_steps=8,
        trace=trace,
        usage=TokenUsage(
            prompt_tokens=tokens - 100,
            completion_tokens=100,
            total_tokens=tokens,
        ),
        latency_ms=4321,
    )


def assessment(status, chunk_ids=()):
    return {
        "requirement": "要求",
        "status": status,
        "reason": "依据",
        "evidence": [
            {"section_type": "skills", "title": "技能", "content": "内容",
             "score": 0.9, "chunk_id": chunk_id}
            for chunk_id in chunk_ids
        ],
    }


def test_derive_observed_outcome_reads_real_trace() -> None:
    match_payload = {
        "assessments": [
            assessment("strong_match", [101, 102]),
            assessment("strong_match", [102]),
        ],
        "summary": {
            "strong_match_count": 2,
            "partial_match_count": 0,
            "insufficient_evidence_count": 0,
        },
    }
    result = make_result(
        [
            make_execution("extract_job_requirements", {"ok": True, "result": {}}),
            make_execution("search_resume_evidence", {"ok": True, "result": {}}),
            make_execution(
                "assess_requirement_match",
                {"ok": True, "result": match_payload},
                step=2,
                call_id="call-3",
            ),
            make_execution(
                "save_match_report",
                {"ok": True, "result": {"saved": True}},
                step=3,
                call_id="call-4",
            ),
        ]
    )

    observed, extras = derive_observed_outcome(result)

    assert observed.task_status == "completed"
    assert observed.tools == [
        "extract_job_requirements",
        "search_resume_evidence",
        "assess_requirement_match",
        "save_match_report",
    ]
    assert observed.tool_call_count == 4
    assert observed.tool_error_count == 0
    # chunk_id 按出现顺序去重。
    assert observed.citation_ids == [101, 102]
    assert observed.match_statuses == ["strong_match", "strong_match"]
    assert observed.abstained is False
    assert observed.suggestion_count == 2
    assert observed.unsupported_suggestion_count == 0
    assert observed.usage_total == 1200
    assert observed.latency_ms == 4321
    assert observed.error_code is None
    assert extras["evidence_backed"] is True
    assert extras["evidence_item_count"] == 3


def test_derive_observed_outcome_counts_tool_errors() -> None:
    result = make_result(
        [
            make_execution("extract_job_requirements", {"ok": True, "result": {}}),
            make_execution(
                "search_resume_evidence",
                {"ok": False, "error": "工具参数校验失败"},
                step=1,
                call_id="call-2",
            ),
        ],
        steps=2,
    )

    observed, extras = derive_observed_outcome(result)

    assert observed.tool_call_count == 2
    assert observed.tool_error_count == 1
    assert observed.match_statuses == []
    assert extras["evidence_backed"] is False


def test_derive_observed_outcome_detects_abstention() -> None:
    match_payload = {
        "assessments": [assessment("insufficient_evidence")],
        "summary": {
            "strong_match_count": 0,
            "partial_match_count": 0,
            "insufficient_evidence_count": 1,
        },
    }
    result = make_result(
        [
            make_execution(
                "assess_requirement_match",
                {"ok": True, "result": match_payload},
            )
        ],
        steps=1,
    )

    observed, extras = derive_observed_outcome(result)

    assert observed.abstained is True
    assert observed.citation_ids == []
    assert observed.unsupported_suggestion_count == 0
    assert extras["evidence_backed"] is True


def test_derive_observed_outcome_flags_unsupported_suggestion() -> None:
    match_payload = {
        "assessments": [assessment("strong_match")],
        "summary": {
            "strong_match_count": 1,
            "partial_match_count": 0,
            "insufficient_evidence_count": 0,
        },
    }
    result = make_result(
        [
            make_execution(
                "assess_requirement_match",
                {"ok": True, "result": match_payload},
            )
        ],
        steps=1,
    )

    observed, extras = derive_observed_outcome(result)

    assert observed.unsupported_suggestion_count == 1
    assert extras["evidence_backed"] is False


def test_max_steps_result_maps_to_interrupted() -> None:
    result = make_result(
        [make_execution("extract_job_requirements", {"ok": True, "result": {}})],
        status="max_steps_reached",
        steps=8,
    )

    observed, _ = derive_observed_outcome(result)

    assert observed.task_status == "interrupted"
    assert observed.error_code == "max_steps_reached"


def test_skip_reason_only_excludes_hitl_and_interrupted() -> None:
    cases = {case.case_id: case for case in load_dataset()}

    assert skip_reason(cases["python_fastapi_happy"]) is None
    assert skip_reason(cases["no_mongodb_abstain"]) is None
    assert skip_reason(cases["confirmation_revise_recovered"]) is not None
    assert skip_reason(cases["user_reject_cancelled"]) is not None
    assert skip_reason(cases["max_steps_interrupted"]) is not None


def test_score_live_observations_reuses_scorer() -> None:
    cases = load_dataset()
    base = cases[0]

    observations = {
        "generated_at": "2026-10-04T00:00:00+00:00",
        "git_revision": "abc1234",
        "model": "test-model",
        "max_steps": 8,
        "executed_cases": [
            {
                "case_id": base.case_id,
                "category": base.category,
                "observed": {
                    "task_status": "completed",
                    "tools": base.expected.tools,
                    "match_statuses": base.expected.match_statuses,
                    "citation_ids": base.expected.citation_ids,
                    "abstained": False,
                    "confirmation_recovered": True,
                    "tool_call_count": 4,
                    "tool_error_count": 0,
                    "suggestion_count": 2,
                    "unsupported_suggestion_count": 0,
                    "steps": 3,
                    "usage_total": 900,
                    "latency_ms": 1500,
                    "error_code": None,
                },
                "extras": {"evidence_backed": True},
            }
        ],
        "skipped_cases": [],
    }

    report, summary, live_cases = score_live_observations(cases, observations)

    assert len(live_cases) == 1
    assert report["executed_case_count"] == 1
    assert report["summary"]["task_completion_rate"] == 1.0
    assert report["summary"]["evidence_backed_rate"] == 1.0
    assert report["thresholds"]["tool_f1"]["passed"] is True
    assert summary.p50_latency_ms == 1500.0
    # 报告必须可 JSON 序列化，保证能落盘。
    json.dumps(report, ensure_ascii=False)


def test_score_live_observations_rejects_empty_observations() -> None:
    cases = load_dataset()

    try:
        score_live_observations(cases, {"executed_cases": []})
    except ValueError as exc:
        assert "没有可评分" in str(exc)
    else:
        raise AssertionError("空观测值必须报错")