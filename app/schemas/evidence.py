# 定义简历证据检索的输入、输出和约束。

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


# 清理单条岗位要求，并校验非空和最大长度。
def _normalize_requirement(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("岗位要求不能为空")

    if len(value) > MAX_REQUIREMENT_LENGTH:
        raise ValueError(
            f"单条岗位要求不能超过 {MAX_REQUIREMENT_LENGTH} 个字符"
        )

    return value


# 表示证据检索工具需要的岗位要求和简历分段。
class EvidenceSearchRequest(BaseModel):
    """简历证据检索的输入。"""

    model_config = ConfigDict(extra="forbid")

    requirements: list[str] = Field(
        min_length=1,
        max_length=MAX_REQUIREMENTS,
        description="需要检索证据的岗位要求列表。",
    )
    sections: list[ResumeSection] | None = Field(
        default=None,
        max_length=100,
        description="旧关键词路径使用的简历分段；RAG 路径可为空。",
    )

    @model_validator(mode="after")
    def validate_optional_sections(self):
        if self.sections is not None and not self.sections:
            raise ValueError("sections 不能为空")

        return self

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


# 表示一段简历原文及其关键词匹配分数。
class EvidenceItem(ResumeSection):
    """一条与岗位要求相关的简历证据。"""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(
        ge=0,
        le=1,
        description="归一化相关性分数，范围 0～1。",
    )
    chunk_id: int | None = Field(
        default=None,
        ge=1,
        description="持久化 Chunk 身份；旧关键词路径可为空。",
    )
    source_version_id: int | None = Field(
        default=None,
        ge=1,
        description="证据来源的简历版本 ID。",
    )
    position: int | None = Field(
        default=None,
        ge=1,
        description="证据在来源版本中的顺序。",
    )
    rerank_score: float | None = Field(
        default=None,
        description="Reranker 原始分数；未重排时为空。",
    )


# 表示一条岗位要求与对应证据列表的绑定关系。
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


# 表示按岗位要求顺序组织的完整证据检索结果。
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
