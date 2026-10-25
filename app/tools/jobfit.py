# 定义并注册 JobFit Agent 的真实工具。

import logging

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.repositories import (
    AnalysisTaskRepository,
    ReportRepository,
    ResumeRepository,
    ResumeVersionRepository,
)
from app.schemas.agent_events import AgentEvent
from app.schemas.evidence import (
    EvidenceSearchRequest,
    EvidenceSearchResult,
)
from app.schemas.extraction import JobExtraction
from app.schemas.matching import MatchAssessmentResult
from app.schemas.resume import ResumeExtraction
from app.services.citation_validation import validate_report_citations
from app.services.evidence_search import search_resume_evidence
from app.services.extraction import extract_job
from app.services.matching import (
    assess_requirement_match,
    merge_similar_assessments,
)
from app.services.rag_evidence import search_requirements_with_rag
from app.services.resume_extraction import (
    MAX_RESUME_TEXT_LENGTH,
    extract_resume_sections,
)
from app.tools.base import ToolContext, ToolSpec
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)
# 定义岗位 JD 提取工具的输入契约。
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


# 定义简历分段提取工具的输入契约。
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


# get_resume_profile 不需要模型传入任何参数。
class GetResumeProfileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


# 定义保存当前分析报告的模型输出契约。
class SaveMatchReportArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(
        min_length=1,
        description="分析报告的简要总结。",
    )
    result_json: dict = Field(
        description="完整的结构化岗位匹配分析结果。",
    )

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("报告总结不能为空")

        return value


# 把岗位 JD 工具参数适配到现有提取服务。
async def extract_job_requirements_handler(
    args: ExtractJobRequirementsArgs,
    context: ToolContext,
) -> dict:
    result: JobExtraction = await extract_job(args.job_description)
    return result.model_dump(mode="json")


# 把简历工具参数适配到现有分段提取服务。
async def extract_resume_sections_handler(
    args: ExtractResumeSectionsArgs,
    context: ToolContext,
) -> dict:
    result: ResumeExtraction = await extract_resume_sections(args.resume_text)
    return result.model_dump(mode="json")


# 从任务快照恢复旧关键词路径需要的 sections。
def _sections_from_context(
    context: ToolContext,
) -> list:
    snapshot = context.resume_profile_snapshot

    if not isinstance(snapshot, dict):
        return []

    extracted_sections = snapshot.get("extracted_sections")
    if not isinstance(extracted_sections, dict):
        return []

    try:
        return ResumeExtraction.model_validate(
            extracted_sections
        ).sections
    except Exception:  # noqa: BLE001
        return []


async def _emit_context_event(
    context: ToolContext,
    *,
    event_type: str,
    data: dict,
) -> None:
    if context.event_sink is None:
        return

    await context.event_sink(
        AgentEvent(
            type=event_type,
            task_id=context.task_id,
            data=data,
        )
    )


# 优先使用 RAG 检索，失败时回退旧关键词检索。
async def search_resume_evidence_handler(
    args: EvidenceSearchRequest,
    context: ToolContext,
) -> dict:
    fallback_sections = args.sections or _sections_from_context(
        context
    )

    if (
        context.rag_enabled
        and context.session_factory is not None
        and context.resume_version_id is not None
    ):
        await _emit_context_event(
            context,
            event_type="retrieval_started",
            data={
                "mode": "hybrid_rerank",
                "requirement_count": len(args.requirements),
            },
        )

        try:
            async with context.session_factory() as session:
                result, evidence_packs = (
                    await search_requirements_with_rag(
                        session,
                        user_id=context.current_user.id,
                        resume_version_id=(
                            context.resume_version_id
                        ),
                        requirements=args.requirements,
                    )
                )
        except Exception:
            logger.warning(
                "RAG 检索失败，尝试旧关键词回退 task_id=%s",
                context.task_id,
                exc_info=True,
            )
            await _emit_context_event(
                context,
                event_type="retrieval_finished",
                data={
                    "mode": "legacy_keyword",
                    "degraded": True,
                    "error_code": "rag_retrieval_failed",
                },
            )
        else:
            context.retrieved_evidence_packs.extend(
                evidence_packs
            )
            await _emit_context_event(
                context,
                event_type="retrieval_finished",
                data={
                    "mode": "hybrid_rerank",
                    "degraded": any(
                        pack.degraded
                        for pack in evidence_packs
                    ),
                    "evidence_counts": [
                        len(pack.items)
                        for pack in evidence_packs
                    ],
                },
            )
            return result.model_dump(mode="json")

    if not fallback_sections:
        raise ValueError(
            "非 RAG 检索必须提供 sections，"
            "或提供可用的持久化 RAG 上下文"
        )

    result = search_resume_evidence(
        requirements=args.requirements,
        sections=fallback_sections,
    )
    await _emit_context_event(
        context,
        event_type="retrieval_finished",
        data={
            "mode": "legacy_keyword",
            "degraded": True,
            "evidence_counts": [
                len(match.evidence)
                for match in result.matches
            ],
        },
    )
    return result.model_dump(mode="json")

# 把结构化检索结果适配到三态匹配评估服务。
async def assess_requirement_match_handler(
    args: EvidenceSearchResult,
    context: ToolContext,
) -> dict:
    result: MatchAssessmentResult = assess_requirement_match(args)
    result = merge_similar_assessments(result)
    return result.model_dump(mode="json")


def _public_resume_profile(snapshot: dict) -> dict:
    """返回可进入模型上下文的最小简历元信息，不含原文和分段正文。"""

    extracted_sections = snapshot.get("extracted_sections")
    section_count = 0
    if isinstance(extracted_sections, dict):
        sections = extracted_sections.get("sections")
        if isinstance(sections, list):
            section_count = len(sections)

    return {
        "found": bool(snapshot.get("found", False)),
        "task_id": snapshot.get("task_id"),
        "resume_id": snapshot.get("resume_id"),
        "resume_version_id": snapshot.get("resume_version_id"),
        "version_no": snapshot.get("version_no"),
        "resume_title": snapshot.get("resume_title"),
        "section_count": section_count,
    }

# 根据当前任务上下文读取当前用户持久化的简历版本。
async def get_resume_profile_handler(
    args: GetResumeProfileArgs,
    context: ToolContext,
) -> dict:
    if context.resume_profile_snapshot is not None:
        return _public_resume_profile(context.resume_profile_snapshot)

    if context.session is None or context.task_id is None:
        return {"found": False}

    user_id = context.current_user.id
    task_repository = AnalysisTaskRepository(context.session)
    version_repository = ResumeVersionRepository(context.session)
    resume_repository = ResumeRepository(context.session)

    task = await task_repository.get_for_user(
        task_id=context.task_id,
        user_id=user_id,
    )
    if task is None:
        return {"found": False}

    resume_version = await version_repository.get_for_user(
        resume_version_id=task.resume_version_id,
        user_id=user_id,
    )
    if resume_version is None:
        return {"found": False}

    resume = await resume_repository.get_for_user(
        resume_id=resume_version.resume_id,
        user_id=user_id,
    )
    if resume is None:
        return {"found": False}

    return _public_resume_profile(
        {
            "found": True,
            "task_id": task.task_id,
            "resume_id": resume.resume_id,
            "resume_version_id": resume_version.resume_version_id,
            "version_no": resume_version.version_no,
            "resume_title": resume.title,
            "extracted_sections": resume_version.extracted_sections,
        }
    )


def _validate_report_citations(
    result_json: dict,
    context: ToolContext,
) -> str | None:
    if not context.rag_enabled:
        return None

    if not context.retrieved_evidence_packs:
        return "报告没有可用证据"

    validation = validate_report_citations(
        result_json=result_json,
        evidence_packs=context.retrieved_evidence_packs,
        require_at_least_one=True,
    )
    if validation.missing_citation:
        return "报告缺少证据引用"
    if validation.unknown_chunk_ids:
        return f"报告引用了未知证据: {validation.unknown_chunk_ids}"
    if validation.duplicate_chunk_ids:
        return f"报告包含重复证据: {validation.duplicate_chunk_ids}"
    return None

# 把模型生成的分析结果保存为当前任务的新报告版本。
async def save_match_report_handler(
    args: SaveMatchReportArgs,
    context: ToolContext,
) -> dict:
    citation_error = _validate_report_citations(
        args.result_json,
        context,
    )
    if citation_error is not None:
        return {
            "saved": False,
            "error": citation_error,
        }

    if context.defer_report_save:
        queued_report = {
            "summary": args.summary,
            "result_json": args.result_json,
        }
        duplicate = context.pending_report == queued_report
        context.pending_report = queued_report
        return {
            "saved": True,
            "queued": True,
            "duplicate": duplicate,
            "message": (
                "报告已进入待确认队列，禁止再次调用 save_match_report。"
                if not duplicate
                else "报告已在队列中，禁止再次调用 save_match_report。"
            ),
        }

    if context.session is None or context.task_id is None:
        return {
            "saved": False,
            "error": "任务不存在或无权访问",
        }

    repository = ReportRepository(context.session)

    try:
        report = await repository.create_for_user(
            task_id=context.task_id,
            user_id=context.current_user.id,
            summary=args.summary,
            result_json=args.result_json,
            make_current=True,
        )
    except LookupError:
        return {
            "saved": False,
            "error": "任务不存在或无权访问",
        }

    return {
        "saved": True,
        "report_id": report.report_id,
        "task_id": report.task_id,
        "version_no": report.version_no,
        "is_current": report.is_current,
    }


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
        "根据岗位要求检索简历证据。持久化 RAG 任务只需传 "
        "requirements，后端会执行混合检索和 Rerank；"
        "旧非 RAG 流程仍需传 sections。"
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


GET_RESUME_PROFILE_TOOL = ToolSpec(
    name="get_resume_profile",
    description=(
        "读取当前分析任务绑定的、属于当前用户的持久化简历版本。"
    ),
    args_model=GetResumeProfileArgs,
    handler=get_resume_profile_handler,
)


SAVE_MATCH_REPORT_TOOL = ToolSpec(
    name="save_match_report",
    description=(
        "把当前任务的结构化岗位匹配结果保存为新的当前报告版本。"
    ),
    args_model=SaveMatchReportArgs,
    handler=save_match_report_handler,
)


# 创建并装配 JobFit 全部真实工具。
def build_jobfit_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(EXTRACT_JOB_REQUIREMENTS_TOOL)
    registry.register(EXTRACT_RESUME_SECTIONS_TOOL)
    registry.register(SEARCH_RESUME_EVIDENCE_TOOL)
    registry.register(ASSESS_REQUIREMENT_MATCH_TOOL)
    registry.register(GET_RESUME_PROFILE_TOOL)
    registry.register(SAVE_MATCH_REPORT_TOOL)
    return registry
