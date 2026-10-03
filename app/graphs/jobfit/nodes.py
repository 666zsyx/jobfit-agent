# 提供 JobFit Graph 的假数据节点，用于验证拓扑和状态流转。

from __future__ import annotations

from typing import Literal

from app.graphs.jobfit.state import (
    ConfirmationDecision,
    JobFitGraphState,
)


def _node_update(node_name: str) -> dict:
    """统一记录当前节点和节点轨迹。"""

    return {
        "current_node": node_name,
        "trace": [node_name],
    }


def prepare_run(state: JobFitGraphState) -> dict:
    """校验运行参数并初始化工作流。"""

    task_id = state.get("task_id")
    job_id = state.get("job_id")
    resume_version_id = state.get("resume_version_id")
    max_steps = state.get("max_steps", 8)

    if task_id is None or task_id <= 0:
        raise ValueError("task_id 必须大于 0")
    if job_id is None or job_id <= 0:
        raise ValueError("job_id 必须大于 0")
    if resume_version_id is None or resume_version_id <= 0:
        raise ValueError("resume_version_id 必须大于 0")
    if max_steps <= 0:
        raise ValueError("max_steps 必须大于 0")

    return {
        **_node_update("prepare_run"),
        "status": "running",
        "current_step": 0,
        "max_steps": max_steps,
        "error_code": None,
    }


def load_context(state: JobFitGraphState) -> dict:
    """阶段一使用假数据模拟读取任务上下文。"""

    return {
        **_node_update("load_context"),
        "context_loaded": True,
        "job_requirement_count": 4,
        "resume_section_count": 3,
    }


def agent_decide(state: JobFitGraphState) -> dict:
    """阶段一确定性地产生一次工具调用。"""

    existing_results = state.get("tool_results", [])

    if not existing_results:
        tool_calls = [
            {
                "id": "fake-call-1",
                "name": "search_resume_evidence",
                "arguments": {
                    "requirements": [
                        "Python",
                        "FastAPI",
                    ]
                },
            }
        ]
    else:
        tool_calls = []

    return {
        **_node_update("agent_decide"),
        "tool_calls": tool_calls,
    }


def execute_tools(state: JobFitGraphState) -> dict:
    """阶段一使用假数据返回工具结果。"""

    tool_calls = state.get("tool_calls", [])
    if not tool_calls:
        return _node_update("execute_tools")

    results = [
        {
            "tool_call_id": call["id"],
            "tool_name": call["name"],
            "status": "success",
            "result": {
                "evidence_ids": ["chunk-fake-1", "chunk-fake-2"]
            },
        }
        for call in tool_calls
    ]

    return {
        **_node_update("execute_tools"),
        "tool_results": results,
        "current_step": state.get("current_step", 0) + len(results),
    }


def assess_evidence(state: JobFitGraphState) -> dict:
    """阶段一把工具结果整理成假 EvidencePack 和待确认报告。"""

    tool_results = state.get("tool_results", [])
    evidence_ids: list[str] = []

    for result in tool_results:
        result_data = result.get("result", {})
        evidence_ids.extend(result_data.get("evidence_ids", []))

    evidence_pack = [
        {
            "chunk_id": evidence_id,
            "summary": f"假证据摘要 {index + 1}",
        }
        for index, evidence_id in enumerate(evidence_ids)
    ]

    return {
        **_node_update("assess_evidence"),
        "evidence_pack": evidence_pack,
        "pending_report": {
            "summary": "假匹配报告",
            "evidence_ids": evidence_ids,
            "status": "pending_confirmation",
        },
    }


def human_confirmation(state: JobFitGraphState) -> dict:
    """阶段一使用普通节点模拟人工确认。

    PART 5 会把这个节点替换为 LangGraph interrupt。
    """

    decision: ConfirmationDecision = (
        state.get("confirmation_decision") or "approve"
    )

    if decision not in {"approve", "revise", "reject"}:
        raise ValueError("confirmation_decision 不合法")

    return {
        **_node_update("human_confirmation"),
        "confirmation_decision": decision,
    }


def save_report(state: JobFitGraphState) -> dict:
    """阶段一使用假报告 ID 模拟保存报告。"""

    return {
        **_node_update("save_report"),
        "report_id": 101,
        "status": "report_saved",
    }


def finalize(state: JobFitGraphState) -> dict:
    """标记工作流成功结束。"""

    return {
        **_node_update("finalize"),
        "status": "completed",
    }


def cancel(state: JobFitGraphState) -> dict:
    """用户拒绝时取消工作流。"""

    return {
        **_node_update("cancel"),
        "status": "cancelled",
        "error_code": "user_rejected",
    }


def route_after_agent(
    state: JobFitGraphState,
) -> Literal["execute_tools", "assess_evidence"]:
    """工具调用存在且未超过最大步数时继续执行工具。"""

    has_tool_calls = bool(state.get("tool_calls"))
    current_step = state.get("current_step", 0)
    max_steps = state.get("max_steps", 8)

    if has_tool_calls and current_step < max_steps:
        return "execute_tools"
    return "assess_evidence"


def route_after_confirmation(
    state: JobFitGraphState,
) -> Literal["save_report", "cancel"]:
    """拒绝时取消，其余情况保存报告。"""

    if state.get("confirmation_decision") == "reject":
        return "cancel"
    return "save_report"


__all__ = [
    "agent_decide",
    "assess_evidence",
    "cancel",
    "execute_tools",
    "finalize",
    "human_confirmation",
    "load_context",
    "prepare_run",
    "route_after_agent",
    "route_after_confirmation",
    "save_report",
]
