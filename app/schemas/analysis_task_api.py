# 定义持久化分析任务的 API 请求和响应契约。

from pydantic import BaseModel, ConfigDict, Field

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
    "PersistedAgentExecutionResult",
]
