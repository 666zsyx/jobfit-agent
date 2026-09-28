# 定义 ReAct Agent 的执行轨迹、状态和最终结果。

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.schemas.chat import TokenUsage


ReactAgentStatus = Literal[
    "completed",
    "max_steps_reached",
]

MAX_AGENT_JOB_DESCRIPTION_LENGTH = 20_000
MAX_AGENT_RESUME_TEXT_LENGTH = 50_000


# 定义 JobFit ReAct 匹配接口的请求参数。
class JobFitAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_description: str = Field(
        min_length=1,
        max_length=MAX_AGENT_JOB_DESCRIPTION_LENGTH,
        description="需要分析的岗位 JD。",
    )
    resume_text: str = Field(
        min_length=1,
        max_length=MAX_AGENT_RESUME_TEXT_LENGTH,
        description="需要分析的简历原文。",
    )

    @field_validator("job_description", "resume_text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("字段不能为空或纯空白")

        return value

# 记录一次工具调用及其完整 Observation。
class ReactToolExecution(BaseModel):
    step: int = Field(
        ge=1,
        description="该工具调用所属的模型决策轮次。",
    )
    tool_call_id: str = Field(
        min_length=1,
        description="模型返回的工具调用 ID。",
    )
    tool_name: str = Field(
        min_length=1,
        description="后端实际执行的注册工具名。",
    )
    arguments: dict[str, Any] | None = Field(
        default=None,
        description="参数校验通过后的工具参数；解析失败时为 None。",
    )
    result: dict[str, Any] = Field(
        description="工具执行器返回的统一结果。",
    )


# 表示一次 ReAct 循环的最终答案和可审计执行结果。
class ReactAgentResult(BaseModel):
    answer: str | None = Field(
        default=None,
        description="模型最终回答；达到最大步数时为空。",
    )
    status: ReactAgentStatus = Field(
        description="循环正常完成或达到最大步数。",
    )
    steps: int = Field(
        ge=1,
        description="实际执行的模型决策轮数。",
    )
    max_steps: int = Field(
        ge=1,
        description="后端允许的最大模型决策轮数。",
    )
    trace: list[ReactToolExecution] = Field(
        default_factory=list,
        description="按真实执行顺序记录的工具调用轨迹。",
    )
    usage: TokenUsage = Field(
        description="所有模型调用累计的 Token Usage。",
    )
    latency_ms: int = Field(
        ge=0,
        description="整个 ReAct 循环的耗时。",
    )


__all__ = [
    "JobFitAgentRequest",
    "MAX_AGENT_JOB_DESCRIPTION_LENGTH",
    "MAX_AGENT_RESUME_TEXT_LENGTH",
    "ReactAgentResult",
    "ReactAgentStatus",
    "ReactToolExecution",
]