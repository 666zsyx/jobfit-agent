# 定义岗位 JD 结构化提取的模型输出契约。

from pydantic import BaseModel, Field, field_validator


# 表示岗位 JD 的结构化提取结果。
class JobExtraction(BaseModel):
    responsibilities: list[str] = Field(
        min_length=1,
        description="岗位职责列表。",
    )
    required_skills: list[str] = Field(
        min_length=1,
        description="必备技能和经验要求列表。",
    )
    nice_to_have: list[str] = Field(
        default_factory=list,
        description="加分项列表。",
    )


# 表示岗位 JD 提取接口的请求参数。
class JobExtractionRequest(BaseModel):
    job_description: str = Field(
        min_length=1,
        max_length=20_000,
        description="需要结构化提取的岗位 JD。",
    )

    @field_validator("job_description")
    @classmethod
    def validate_job_description(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("岗位描述不能为空")

        return value
