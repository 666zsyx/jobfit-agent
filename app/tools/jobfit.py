from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.evidence import (
    EvidenceSearchRequest,
    EvidenceSearchResult,
)
from app.schemas.extraction import JobExtraction
from app.schemas.matching import MatchAssessmentResult
from app.schemas.resume import ResumeExtraction
from app.services.evidence_search import search_resume_evidence
from app.services.extraction import extract_job
from app.services.matching import assess_requirement_match
from app.services.resume_extraction import (
    MAX_RESUME_TEXT_LENGTH,
    extract_resume_sections,
)
from app.tools.base import ToolContext, ToolSpec
from app.tools.registry import ToolRegistry


class ExtractJobRequirementsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_description: str = Field(
        min_length=1,
        max_length=20_000,
        description="需要结构化提取岗位职责、必备技能和加分项的岗位 JD。",
    )

    @field_validator("job_description")
    @classmethod
    def validate_job_description(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("岗位描述不能为空")

        return value


class ExtractResumeSectionsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_text: str = Field(
        min_length=1,
        max_length=MAX_RESUME_TEXT_LENGTH,
        description="需要结构化分段的候选人简历原文。",
    )

    @field_validator("resume_text")
    @classmethod
    def validate_resume_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("简历文本不能为空")

        return value


async def extract_job_requirements_handler(
    args: ExtractJobRequirementsArgs,
    context: ToolContext,
) -> dict:
    result: JobExtraction = await extract_job(args.job_description)
    return result.model_dump(mode="json")


async def extract_resume_sections_handler(
    args: ExtractResumeSectionsArgs,
    context: ToolContext,
) -> dict:
    result: ResumeExtraction = await extract_resume_sections(args.resume_text)
    return result.model_dump(mode="json")


async def search_resume_evidence_handler(
    args: EvidenceSearchRequest,
    context: ToolContext,
) -> dict:
    result: EvidenceSearchResult = search_resume_evidence(
        requirements=args.requirements,
        sections=args.sections,
    )
    return result.model_dump(mode="json")


async def assess_requirement_match_handler(
    args: EvidenceSearchResult,
    context: ToolContext,
) -> dict:
    result: MatchAssessmentResult = assess_requirement_match(args)
    return result.model_dump(mode="json")


EXTRACT_JOB_REQUIREMENTS_TOOL = ToolSpec(
    name="extract_job_requirements",
    description=(
        "从用户提供的岗位 JD 中提取岗位职责、"
        "必备技能和加分项。"
    ),
    args_model=ExtractJobRequirementsArgs,
    handler=extract_job_requirements_handler,
)


EXTRACT_RESUME_SECTIONS_TOOL = ToolSpec(
    name="extract_resume_sections",
    description=(
        "从候选人简历原文中提取教育、工作、项目、技能等"
        "结构化分段，不得总结或改写原文。"
    ),
    args_model=ExtractResumeSectionsArgs,
    handler=extract_resume_sections_handler,
)


SEARCH_RESUME_EVIDENCE_TOOL = ToolSpec(
    name="search_resume_evidence",
    description=(
        "根据岗位要求和已结构化的简历分段，"
        "检索对应的简历原文证据。"
    ),
    args_model=EvidenceSearchRequest,
    handler=search_resume_evidence_handler,
)


ASSESS_REQUIREMENT_MATCH_TOOL = ToolSpec(
    name="assess_requirement_match",
    description=(
        "根据岗位要求和带原文证据的检索结果，"
        "评估每条要求的证据状态：strong_match、"
        "partial_match 或 insufficient_evidence。"
    ),
    args_model=EvidenceSearchResult,
    handler=assess_requirement_match_handler,
)


def build_jobfit_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(EXTRACT_JOB_REQUIREMENTS_TOOL)
    registry.register(EXTRACT_RESUME_SECTIONS_TOOL)
    registry.register(SEARCH_RESUME_EVIDENCE_TOOL)
    registry.register(ASSESS_REQUIREMENT_MATCH_TOOL)
    return registry

