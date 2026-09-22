from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.resume import ResumeSection


MAX_REQUIREMENT_LENGTH = 500
MAX_REQUIREMENTS = 20
MAX_EVIDENCE_PER_REQUIREMENT = 10


def _normalize_requirement(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("岗位要求不能为空")

    if len(value) > MAX_REQUIREMENT_LENGTH:
        raise ValueError(
            f"单条岗位要求不能超过 {MAX_REQUIREMENT_LENGTH} 个字符"
        )

    return value


class EvidenceSearchRequest(BaseModel):
    """简历证据检索的输入。"""

    model_config = ConfigDict(extra="forbid")

    requirements: list[str] = Field(
        min_length=1,
        max_length=MAX_REQUIREMENTS,
        description="需要检索证据的岗位要求列表。",
    )
    sections: list[ResumeSection] = Field(
        min_length=1,
        max_length=100,
        description="已经结构化提取的简历分段列表。",
    )

    @field_validator("requirements")
    @classmethod
    def validate_requirements(
        cls,
        values: list[str],
    ) -> list[str]:
        return [
            _normalize_requirement(value)
            for value in values
        ]


class EvidenceItem(ResumeSection):
    """一条与岗位要求相关的简历证据。"""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(
        ge=0,
        le=1,
        description="关键词匹配分数，范围 0～1。",
    )


class RequirementEvidence(BaseModel):
    """一条岗位要求及其对应的证据列表。"""

    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(
        min_length=1,
        max_length=MAX_REQUIREMENT_LENGTH,
        description="原始岗位要求。",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        max_length=MAX_EVIDENCE_PER_REQUIREMENT,
        description="相关简历证据；没有证据时为空列表。",
    )

    @field_validator("requirement")
    @classmethod
    def validate_requirement(cls, value: str) -> str:
        return _normalize_requirement(value)


class EvidenceSearchResult(BaseModel):
    """完整的简历证据检索结果。"""

    model_config = ConfigDict(extra="forbid")

    requirements: list[str] = Field(
        min_length=1,
        max_length=MAX_REQUIREMENTS,
        description="本次检索使用的岗位要求，用于校验一一对应。",
    )
    matches: list[RequirementEvidence] = Field(
        min_length=1,
        max_length=MAX_REQUIREMENTS,
        description="每条岗位要求对应的证据结果。",
    )

    @field_validator("requirements")
    @classmethod
    def validate_requirements(
        cls,
        values: list[str],
    ) -> list[str]:
        return [
            _normalize_requirement(value)
            for value in values
        ]

    @model_validator(mode="after")
    def validate_matches(self):
        actual_requirements = [
            match.requirement
            for match in self.matches
        ]

        if actual_requirements != self.requirements:
            raise ValueError(
                "matches 必须与 requirements "
                "一一对应，并且顺序完全一致"
            )

        return self