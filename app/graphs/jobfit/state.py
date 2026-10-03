# 定义 JobFit LangGraph 的显式状态结构。

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


ConfirmationDecision = Literal["approve", "revise", "reject"]


class JobFitGraphState(TypedDict, total=False):
    """工作流节点共享的最小状态。

    阶段一先使用假数据验证拓扑，不保存数据库 Session、API Key
    或隐藏思维链。真实 RAG 证据将在后续阶段通过 ID 和摘要接入。
    """

    task_id: int
    job_id: int
    resume_version_id: int

    max_steps: int
    current_step: int
    context_loaded: bool
    job_requirement_count: int
    resume_section_count: int

    tool_calls: list[dict[str, Any]]
    tool_results: Annotated[list[dict[str, Any]], operator.add]
    evidence_pack: list[dict[str, Any]]
    pending_report: dict[str, Any]

    confirmation_decision: ConfirmationDecision | None
    report_id: int | None

    status: str
    current_node: str
    error_code: str | None
    trace: Annotated[list[str], operator.add]


__all__ = [
    "ConfirmationDecision",
    "JobFitGraphState",
]
