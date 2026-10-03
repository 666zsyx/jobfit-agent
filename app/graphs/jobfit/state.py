# 定义 JobFit LangGraph 的显式状态结构。

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


ConfirmationDecision = Literal["approve", "revise", "reject"]
ReactStatus = Literal["completed", "max_steps_reached"]


class JobFitGraphState(TypedDict, total=False):
    """工作流节点共享的状态。

    运行时依赖通过 LangGraph context 注入，不进入 State。
    State 只保存可序列化的工作流数据，便于后续接入 Checkpoint。
    """

    task_id: int
    job_id: int
    resume_version_id: int

    job_description: str
    resume_text: str
    conversation_context: str | None
    system_prompt: str

    max_steps: int
    current_step: int
    context_loaded: bool

    messages: Annotated[list[dict[str, Any]], operator.add]
    tool_calls: list[dict[str, Any]]
    tool_trace: Annotated[list[dict[str, Any]], operator.add]
    tool_audit_events: Annotated[list[dict[str, Any]], operator.add]
    retrieved_evidence_packs: list[dict[str, Any]]

    usage: dict[str, int]
    final_answer: str | None
    react_status: ReactStatus | None
    pending_report: dict[str, Any] | None
    reviewed_report: dict[str, Any] | None
    resume_revision_text: str | None

    confirmation_decision: ConfirmationDecision | None
    report_id: int | None

    status: str
    current_node: str
    error_code: str | None
    trace: Annotated[list[str], operator.add]


__all__ = [
    "ConfirmationDecision",
    "JobFitGraphState",
    "ReactStatus",
]
