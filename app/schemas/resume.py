from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ResumeSectionType = Literal[
    "summary",
    "education",
    "work_experience",
    "project_experience",
    "skills",
    "certificates",
    "other",
]


class ResumeSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_type: ResumeSectionType = Field(
        description="简历分段类型。",
    )
    title: str = Field(
        min_length=1,
        max_length=100,
        description="简历分段的原文标题；原文没有标题时，使用不补充事实的中性标签。",
    )
    content: str = Field(
        min_length=1,
        max_length=20_000,
        description="该分段对应的简历原文内容。",
    )

    @field_validator("title", "content")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("简历分段标题和内容不能为空")

        return value


class ResumeExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[ResumeSection] = Field(
        min_length=1,
        max_length=100,
        description="从简历原文中提取出的分段列表。",
    )
