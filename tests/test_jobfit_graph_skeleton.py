# 验证 JobFit Graph 骨架的拓扑、状态流转和条件路由。

import pytest

from app.graphs.jobfit.graph import build_jobfit_graph
from app.graphs.jobfit.nodes import prepare_run, route_after_agent


def make_initial_state(**overrides) -> dict:
    state = {
        "task_id": 1,
        "job_id": 2,
        "resume_version_id": 3,
        "max_steps": 8,
        "trace": [],
    }
    state.update(overrides)
    return state


def test_graph_runs_fake_happy_path() -> None:
    graph = build_jobfit_graph()

    result = graph.invoke(make_initial_state())

    assert result["status"] == "completed"
    assert result["report_id"] == 101
    assert result["current_step"] == 1
    assert len(result["tool_results"]) == 1
    assert len(result["evidence_pack"]) == 2
    assert result["trace"] == [
        "prepare_run",
        "load_context",
        "agent_decide",
        "execute_tools",
        "agent_decide",
        "assess_evidence",
        "human_confirmation",
        "save_report",
        "finalize",
    ]


def test_graph_rejects_without_saving_report() -> None:
    graph = build_jobfit_graph()

    result = graph.invoke(
        make_initial_state(confirmation_decision="reject")
    )

    assert result["status"] == "cancelled"
    assert result["error_code"] == "user_rejected"
    assert result.get("report_id") is None
    assert result["trace"][-1] == "cancel"


def test_route_stops_tool_loop_at_max_steps() -> None:
    assert (
        route_after_agent(
            {
                "tool_calls": [{"id": "call-1"}],
                "current_step": 0,
                "max_steps": 1,
            }
        )
        == "execute_tools"
    )
    assert (
        route_after_agent(
            {
                "tool_calls": [{"id": "call-1"}],
                "current_step": 1,
                "max_steps": 1,
            }
        )
        == "assess_evidence"
    )


def test_prepare_run_validates_required_identifiers() -> None:
    with pytest.raises(ValueError):
        prepare_run(
            {
                "task_id": 0,
                "job_id": 2,
                "resume_version_id": 3,
                "max_steps": 8,
            }
        )
