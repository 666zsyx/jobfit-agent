from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.evidence import (
    MAX_EVIDENCE_PER_REQUIREMENT,
    MAX_REQUIREMENTS,
    MAX_REQUIREMENT_LENGTH,
    EvidenceItem,
)


MatchStatus = Literal[
    "strong_match",
    "partial_match",
    "insufficient_evidence",
]


class RequirementAssessment(BaseModel):
    """单条岗位要求的证据充分性评估。"""

    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(
        min_length=1,
        max_length=MAX_REQUIREMENT_LENGTH,
        description="原始岗位要求。",
    )
    status: MatchStatus = Field(
        description="基于当前证据得出的匹配状态。",
    )
    reason: str = Field(
        min_length=1,
        description="得出该状态的简要依据。",
    )
    evidence: list[EvidenceItem] = Field(
        max_length=MAX_EVIDENCE_PER_REQUIREMENT,
        description="该要求对应的原文证据；没有证据时为空列表。",
    )

    @field_validator("requirement", "reason")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("字段不能为空或纯空白")

        return value


class MatchSummary(BaseModel):
    """匹配评估结果的汇总统计。"""

    model_config = ConfigDict(extra="forbid")

    strong_match_count: int = Field(
        ge=0,
        description="strong_match 数量。",
    )
    partial_match_count: int = Field(
        ge=0,
        description="partial_match 数量。",
    )
    insufficient_evidence_count: int = Field(
        ge=0,
        description="insufficient_evidence 数量。",
    )


class MatchAssessmentResult(BaseModel):
    """完整的岗位要求匹配评估结果。"""

    model_config = ConfigDict(extra="forbid")

    assessments: list[RequirementAssessment] = Field(
        min_length=1,
        max_length=MAX_REQUIREMENTS,
        description="按岗位要求顺序排列的评估结果。",
    )
    summary: MatchSummary

    @model_validator(mode="after")
    def validate_summary(self):
        actual_counts = {
            "strong_match": 0,
            "partial_match": 0,
            "insufficient_evidence": 0,
        }

        for assessment in self.assessments:
            actual_counts[assessment.status] += 1

        expected_counts = {
            "strong_match": self.summary.strong_match_count,
            "partial_match": self.summary.partial_match_count,
            "insufficient_evidence": (
                self.summary.insufficient_evidence_count
            ),
        }

        if actual_counts != expected_counts:
            raise ValueError(
                "summary 各状态数量必须与 assessments 一致"
            )

        return self


__all__ = [
    "MatchAssessmentResult",
    "MatchStatus",
    "MatchSummary",
    "RequirementAssessment",
]
