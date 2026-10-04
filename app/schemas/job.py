# 定义岗位持久化 API 的请求和响应契约。

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.extraction import JobExtraction


class JobCreateRequest(BaseModel):
    """创建当前用户岗位的请求。"""

    model_config = ConfigDict(extra="forbid")

    job_description: str = Field(
        min_length=1,
        max_length=20_000,
        description="岗位 JD 原文。",
    )
    title: str | None = Field(
        default=None,
        max_length=200,
        description="岗位名称。",
    )
    company_name: str | None = Field(
        default=None,
        max_length=200,
        description="公司名称。",
    )
    extracted_requirements: JobExtraction | None = Field(
        default=None,
        description="可选的岗位结构化提取结果。",
    )

    @field_validator("job_description")
    @classmethod
    def validate_job_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("岗位描述不能为空")
        return value

    @field_validator("title", "company_name")
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class JobUpdateRequest(BaseModel):
    """编辑岗位时允许更新的字段。"""

    model_config = ConfigDict(extra="forbid")

    job_description: str | None = Field(
        default=None,
        max_length=20_000,
        description="岗位 JD 原文。",
    )
    title: str | None = Field(
        default=None,
        max_length=200,
        description="岗位名称。",
    )
    company_name: str | None = Field(
        default=None,
        max_length=200,
        description="公司名称。",
    )
    extracted_requirements: JobExtraction | None = Field(
        default=None,
        description="岗位结构化提取结果；传 null 表示清空。",
    )

    @field_validator("job_description")
    @classmethod
    def validate_job_description(
        cls,
        value: str | None,
    ) -> str:
        if value is None:
            raise ValueError("岗位描述不能为空")
        value = value.strip()
        if not value:
            raise ValueError("岗位描述不能为空")
        return value

    @field_validator("title", "company_name")
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class JobSummary(BaseModel):
    """岗位列表项。"""

    job_id: int = Field(gt=0)
    title: str | None = None
    company_name: str | None = None
    status: str
    job_description_preview: str
    has_extracted_requirements: bool
    created_at: datetime
    updated_at: datetime


class JobDetail(JobSummary):
    """岗位详情。"""

    job_description: str
    extracted_requirements: dict[str, Any] | None = None


class JobDeleteResponse(BaseModel):
    """岗位软删除结果。"""

    job_id: int = Field(gt=0)
    deleted: bool = True


__all__ = [
    "JobCreateRequest",
    "JobDeleteResponse",
    "JobDetail",
    "JobSummary",
    "JobUpdateRequest",
]
