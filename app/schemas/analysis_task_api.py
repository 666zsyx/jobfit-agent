# 定义持久化分析任务的 API 请求和响应契约。

from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.schemas.chat import TokenUsage


class AnalysisTaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int = Field(gt=0, description="当前用户拥有的岗位 ID。")
    resume_version_id: int = Field(
        gt=0,
        description="当前用户拥有的简历版本 ID。",
    )
    conversation_id: int | None = Field(
        default=None,
        gt=0,
        description="可选的当前用户会话 ID。",
    )


class AnalysisTaskResponse(BaseModel):
    task_id: int
    status: str
    current_step: int
    attempt: int
    max_steps: int
    current_node: str | None = None


class AnalysisTaskSummary(BaseModel):
    """任务列表项及其展示所需上下文。"""

    task_id: int = Field(gt=0)
    job_id: int = Field(gt=0)
    resume_version_id: int = Field(gt=0)
    conversation_id: int | None = None
    job_title: str | None = None
    company_name: str | None = None
    job_description_preview: str
    resume_title: str
    status: str
    current_step: int = Field(ge=0)
    attempt: int = Field(ge=0)
    max_steps: int = Field(gt=0)
    current_node: str | None = None
    report_id: int | None = None
    report_version: int | None = None
    metrics_json: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ReportResponse(BaseModel):
    """当前任务报告详情。"""

    report_id: int = Field(gt=0)
    task_id: int = Field(gt=0)
    version_no: int = Field(gt=0)
    is_current: bool
    summary: str
    result_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


ConfirmationDecision = Literal["approve", "revise", "reject"]


class GraphTaskConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ConfirmationDecision
    edited_report: dict | None = None
    resume_revision_text: str | None = Field(
        default=None,
        max_length=50_000,
    )

    @model_validator(mode="after")
    def validate_revision(self):
        if self.decision != "revise":
            return self

        if self.edited_report is None and not (
            self.resume_revision_text and self.resume_revision_text.strip()
        ):
            raise ValueError(
                "revise 必须提供 edited_report 或 resume_revision_text"
            )
        return self


class GraphTaskExecutionResult(BaseModel):
    task_id: int
    status: str
    current_node: str | None = None
    current_step: int = 0
    interrupted: bool = False
    final_answer: str | None = None
    report_id: int | None = None
    report_version: int | None = None
    metrics_json: dict[str, Any] | None = None
    new_resume_version_id: int | None = None
    pending_confirmation: dict | None = None
    usage: dict[str, int] | None = None


class PersistedAgentExecutionResult(BaseModel):
    task_id: int
    status: str
    answer: str | None
    steps: int
    max_steps: int
    usage: TokenUsage
    latency_ms: int
    report_id: int
    report_version: int


__all__ = [
    "AnalysisTaskCreateRequest",
    "AnalysisTaskResponse",
    "AnalysisTaskSummary",
    "ReportResponse",
    "ConfirmationDecision",
    "GraphTaskConfirmationRequest",
    "GraphTaskExecutionResult",
    "PersistedAgentExecutionResult",
]
