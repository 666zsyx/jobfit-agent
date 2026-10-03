# 定义 ReAct 执行前需要的无数据库快照。

from pydantic import BaseModel, ConfigDict, Field


class AnalysisTaskRunSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    username: str = Field(min_length=1)
    role: str = Field(min_length=1)
    job_id: int = Field(gt=0)
    job_description: str = Field(min_length=1)
    resume_profile: dict
    conversation_id: int | None = Field(default=None, gt=0)
    conversation_context: str | None = None
    max_steps: int = Field(gt=0)
    previous_current_step: int = Field(ge=0)
    attempt: int = Field(gt=0)


__all__ = ["AnalysisTaskRunSnapshot"]

