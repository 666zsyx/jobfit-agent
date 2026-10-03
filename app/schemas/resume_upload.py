# 定义简历上传和查询接口的数据结构。

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResumeUploadResponse(BaseModel):
    resume_id: int = Field(gt=0)
    resume_version_id: int = Field(gt=0)
    version_no: int = Field(gt=0)
    title: str
    source_type: str
    char_count: int = Field(ge=1)
    preview: str


class ResumeVersionSummary(BaseModel):
    resume_version_id: int = Field(gt=0)
    version_no: int = Field(gt=0)
    source_type: str
    char_count: int = Field(ge=1)
    preview: str
    created_at: datetime


class ResumeSummary(BaseModel):
    resume_id: int = Field(gt=0)
    title: str
    status: str
    latest_version_no: int = Field(ge=0)
    latest_source_type: str | None = None
    latest_char_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime


class ResumeDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_id: int = Field(gt=0)
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    versions: list[ResumeVersionSummary] = Field(default_factory=list)


__all__ = [
    "ResumeDetail",
    "ResumeSummary",
    "ResumeUploadResponse",
    "ResumeVersionSummary",
]
