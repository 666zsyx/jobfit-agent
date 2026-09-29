# 验证六个 JobFit 工具的注册、参数校验和执行结果。

import asyncio

import pytest
from pydantic import ValidationError

from app.schemas.auth import CurrentUser
from app.schemas.evidence import (
    EvidenceItem,
    EvidenceSearchResult,
    RequirementEvidence,
)
from app.schemas.extraction import JobExtraction
from app.schemas.matching import (
    MatchAssessmentResult,
    MatchSummary,
    RequirementAssessment,
)
from app.schemas.resume import ResumeExtraction, ResumeSection
from app.services.resume_extraction import MAX_RESUME_TEXT_LENGTH
from app.tools import ToolContext
from app.tools.executor import execute_tool
from app.tools import jobfit


VALID_JOB_DESCRIPTION = "负责 FastAPI 后端开发，要求熟悉 Python。"
VALID_RESUME_TEXT = "教育经历\n某大学 计算机科学"

def make_context() -> ToolContext:
    return ToolContext(
        current_user=CurrentUser(
            id=1,
            username="demo_user",
            role="admin",
        )
    )


def make_extraction() -> JobExtraction:
    return JobExtraction(
        responsibilities=["负责 FastAPI 后端开发"],
        required_skills=["熟悉 Python"],
        nice_to_have=[],
    )


def make_resume_extraction() -> ResumeExtraction:
    return ResumeExtraction(
        sections=[
            ResumeSection(
                section_type="education",
                title="教育经历",
                content="某大学 计算机科学",
            )
        ]
    )


def test_jobfit_registry_contains_extract_job_requirements():
    registry = jobfit.build_jobfit_tool_registry()

    tool = registry.get("extract_job_requirements")

    assert tool is jobfit.EXTRACT_JOB_REQUIREMENTS_TOOL


def test_jobfit_registry_contains_six_tools():
    registry = jobfit.build_jobfit_tool_registry()

    assert registry.get("extract_job_requirements") is (
        jobfit.EXTRACT_JOB_REQUIREMENTS_TOOL
    )
    assert registry.get("extract_resume_sections") is (
        jobfit.EXTRACT_RESUME_SECTIONS_TOOL
    )
    assert registry.get("search_resume_evidence") is (
        jobfit.SEARCH_RESUME_EVIDENCE_TOOL
    )
    assert registry.get("assess_requirement_match") is (
        jobfit.ASSESS_REQUIREMENT_MATCH_TOOL
    )
    assert registry.get("get_resume_profile") is (
        jobfit.GET_RESUME_PROFILE_TOOL
    )
    assert registry.get("save_match_report") is (
        jobfit.SAVE_MATCH_REPORT_TOOL
    )
    assert len(registry.openai_definitions()) == 6


def test_get_resume_profile_definition_has_empty_schema():
    registry = jobfit.build_jobfit_tool_registry()

    definition = next(
        item
        for item in registry.openai_definitions()
        if item["function"]["name"] == "get_resume_profile"
    )
    parameters = definition["function"]["parameters"]

    assert parameters["type"] == "object"
    assert parameters["properties"] == {}
    assert "required" not in parameters
    assert parameters["additionalProperties"] is False


def test_save_match_report_definition_has_expected_schema():
    registry = jobfit.build_jobfit_tool_registry()

    definition = next(
        item
        for item in registry.openai_definitions()
        if item["function"]["name"] == "save_match_report"
    )
    parameters = definition["function"]["parameters"]

    assert set(parameters["properties"]) == {
        "summary",
        "result_json",
    }
    assert parameters["required"] == [
        "summary",
        "result_json",
    ]
    assert parameters["additionalProperties"] is False


def test_save_match_report_rejects_blank_summary():
    with pytest.raises(ValidationError):
        jobfit.SaveMatchReportArgs(
            summary="   ",
            result_json={},
        )


def test_tool_context_session_is_excluded_from_model_dump():
    context = make_context()

    assert context.session is None
    assert context.task_id is None
    assert context.step_no is None
    assert "session" not in context.model_dump()
    assert "resume_profile_snapshot" not in context.model_dump()
    assert "pending_report" not in context.model_dump()
    assert "defer_report_save" not in context.model_dump()
    assert "collect_tool_audit" not in context.model_dump()
    assert "tool_audit_events" not in context.model_dump()


def test_get_resume_profile_prefers_snapshot():
    snapshot = {
        "found": True,
        "task_id": 7,
        "resume_id": 8,
        "resume_version_id": 9,
        "version_no": 2,
        "resume_title": "Snapshot Resume",
        "raw_text": "snapshot text",
        "extracted_sections": {"sections": []},
    }
    context = ToolContext(
        current_user=CurrentUser(
            id=1,
            username="demo_user",
            role="admin",
        ),
        task_id=7,
        resume_profile_snapshot=snapshot,
    )

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="get_resume_profile",
            arguments={},
            context=context,
        )
    )

    assert result == {"ok": True, "result": snapshot}


def test_save_match_report_can_defer_persistence():
    context = ToolContext(
        current_user=CurrentUser(
            id=1,
            username="demo_user",
            role="admin",
        ),
        task_id=7,
        defer_report_save=True,
    )

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="save_match_report",
            arguments={
                "summary": "Deferred report",
                "result_json": {"matches": []},
            },
            context=context,
        )
    )

    assert result == {
        "ok": True,
        "result": {
            "saved": True,
            "queued": True,
        },
    }
    assert context.pending_report == {
        "summary": "Deferred report",
        "result_json": {"matches": []},
    }


def test_extract_job_requirements_definition_has_expected_schema():
    registry = jobfit.build_jobfit_tool_registry()

    definition = registry.openai_definitions()[0]
    function = definition["function"]
    parameters = function["parameters"]

    assert function["name"] == "extract_job_requirements"
    assert "岗位职责" in function["description"]
    assert "必备技能" in function["description"]
    assert "加分项" in function["description"]
    assert parameters["type"] == "object"
    assert "job_description" in parameters["properties"]
    assert parameters["properties"]["job_description"]["maxLength"] == 20_000
    assert parameters["required"] == ["job_description"]
    assert parameters["additionalProperties"] is False


def test_extract_resume_sections_definition_has_expected_schema():
    registry = jobfit.build_jobfit_tool_registry()

    definitions = registry.openai_definitions()
    definition = next(
        item
        for item in definitions
        if item["function"]["name"] == "extract_resume_sections"
    )
    function = definition["function"]
    parameters = function["parameters"]

    assert "简历原文" in function["description"]
    assert "结构化分段" in function["description"]
    assert parameters["type"] == "object"
    assert "resume_text" in parameters["properties"]
    assert (
        parameters["properties"]["resume_text"]["maxLength"]
        == MAX_RESUME_TEXT_LENGTH
    )
    assert parameters["required"] == ["resume_text"]
    assert parameters["additionalProperties"] is False


def test_extract_job_requirements_calls_existing_service(monkeypatch):
    calls: list[str] = []

    async def fake_extract_job(job_description: str) -> JobExtraction:
        calls.append(job_description)
        return make_extraction()

    monkeypatch.setattr(jobfit, "extract_job", fake_extract_job)

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="extract_job_requirements",
            arguments={"job_description": VALID_JOB_DESCRIPTION},
            context=make_context(),
        )
    )

    assert calls == [VALID_JOB_DESCRIPTION]
    assert result == {
        "ok": True,
        "result": {
            "responsibilities": ["负责 FastAPI 后端开发"],
            "required_skills": ["熟悉 Python"],
            "nice_to_have": [],
        },
    }


def test_extract_resume_sections_calls_existing_service(monkeypatch):
    calls: list[str] = []

    async def fake_extract_resume_sections(
        resume_text: str,
    ) -> ResumeExtraction:
        calls.append(resume_text)
        return make_resume_extraction()

    monkeypatch.setattr(
        jobfit,
        "extract_resume_sections",
        fake_extract_resume_sections,
    )

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="extract_resume_sections",
            arguments={"resume_text": VALID_RESUME_TEXT},
            context=make_context(),
        )
    )

    assert calls == [VALID_RESUME_TEXT]
    assert result == {
        "ok": True,
        "result": {
            "sections": [
                {
                    "section_type": "education",
                    "title": "教育经历",
                    "content": "某大学 计算机科学",
                }
            ]
        },
    }


@pytest.mark.parametrize(
    "job_description",
    [
        "",
        "   ",
        "a" * 20_001,
    ],
)
def test_extract_job_requirements_rejects_invalid_description(
    monkeypatch,
    job_description: str,
):
    calls: list[str] = []

    async def fake_extract_job(value: str) -> JobExtraction:
        calls.append(value)
        return make_extraction()

    monkeypatch.setattr(jobfit, "extract_job", fake_extract_job)

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="extract_job_requirements",
            arguments={"job_description": job_description},
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具参数校验失败",
    }
    assert calls == []


@pytest.mark.parametrize(
    "resume_text",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="spaces"),
        pytest.param("\n\t", id="newlines"),
        pytest.param(
            "a" * (MAX_RESUME_TEXT_LENGTH + 1),
            id="too-long",
        ),
    ],
)
def test_extract_resume_sections_rejects_invalid_text(
    monkeypatch,
    resume_text: str,
):
    calls: list[str] = []

    async def fake_extract_resume_sections(
        value: str,
    ) -> ResumeExtraction:
        calls.append(value)
        return make_resume_extraction()

    monkeypatch.setattr(
        jobfit,
        "extract_resume_sections",
        fake_extract_resume_sections,
    )

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="extract_resume_sections",
            arguments={"resume_text": resume_text},
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具参数校验失败",
    }
    assert calls == []


def test_extract_job_requirements_rejects_extra_arguments(monkeypatch):
    calls: list[str] = []

    async def fake_extract_job(job_description: str) -> JobExtraction:
        calls.append(job_description)
        return make_extraction()

    monkeypatch.setattr(jobfit, "extract_job", fake_extract_job)

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="extract_job_requirements",
            arguments={
                "job_description": VALID_JOB_DESCRIPTION,
                "user_id": 999,
            },
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具参数校验失败",
    }
    assert calls == []


def test_extract_resume_sections_rejects_extra_arguments(monkeypatch):
    calls: list[str] = []

    async def fake_extract_resume_sections(
        resume_text: str,
    ) -> ResumeExtraction:
        calls.append(resume_text)
        return make_resume_extraction()

    monkeypatch.setattr(
        jobfit,
        "extract_resume_sections",
        fake_extract_resume_sections,
    )

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="extract_resume_sections",
            arguments={
                "resume_text": VALID_RESUME_TEXT,
                "user_id": 999,
            },
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具参数校验失败",
    }
    assert calls == []


def test_extract_job_requirements_strips_description(monkeypatch):
    calls: list[str] = []

    async def fake_extract_job(job_description: str) -> JobExtraction:
        calls.append(job_description)
        return make_extraction()

    monkeypatch.setattr(jobfit, "extract_job", fake_extract_job)

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="extract_job_requirements",
            arguments={"job_description": f"  {VALID_JOB_DESCRIPTION}  "},
            context=make_context(),
        )
    )

    assert result["ok"] is True
    assert calls == [VALID_JOB_DESCRIPTION]

VALID_EVIDENCE_REQUIREMENTS = ["熟悉 Python"]
VALID_EVIDENCE_SECTIONS = [
    {
        "section_type": "skills",
        "title": "技能",
        "content": "Python、FastAPI、Pydantic",
    }
]


def make_evidence_result() -> EvidenceSearchResult:
    return EvidenceSearchResult(
        requirements=VALID_EVIDENCE_REQUIREMENTS,
        matches=[
            RequirementEvidence(
                requirement="熟悉 Python",
                evidence=[
                    EvidenceItem(
                        section_type="skills",
                        title="技能",
                        content="Python、FastAPI、Pydantic",
                        score=0.5,
                    )
                ],
            )
        ],
    )


def test_search_resume_evidence_definition_has_expected_schema():
    registry = jobfit.build_jobfit_tool_registry()

    definitions = registry.openai_definitions()
    definition = next(
        item
        for item in definitions
        if item["function"]["name"] == "search_resume_evidence"
    )
    function = definition["function"]
    parameters = function["parameters"]

    assert "岗位要求" in function["description"]
    assert "简历分段" in function["description"]
    assert "原文证据" in function["description"]
    assert parameters["type"] == "object"
    assert "requirements" in parameters["properties"]
    assert "sections" in parameters["properties"]
    assert parameters["required"] == ["requirements", "sections"]
    assert parameters["additionalProperties"] is False
    assert "max_evidence_per_requirement" not in parameters["properties"]


def test_search_resume_evidence_calls_existing_service(monkeypatch):
    calls: list[tuple[list[str], list[ResumeSection]]] = []

    def fake_search_resume_evidence(
        requirements: list[str],
        sections: list[ResumeSection],
    ) -> EvidenceSearchResult:
        calls.append((requirements, sections))
        return make_evidence_result()

    monkeypatch.setattr(
        jobfit,
        "search_resume_evidence",
        fake_search_resume_evidence,
    )

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="search_resume_evidence",
            arguments={
                "requirements": VALID_EVIDENCE_REQUIREMENTS,
                "sections": VALID_EVIDENCE_SECTIONS,
            },
            context=make_context(),
        )
    )

    assert calls == [
        (
            VALID_EVIDENCE_REQUIREMENTS,
            [ResumeSection.model_validate(VALID_EVIDENCE_SECTIONS[0])],
        )
    ]
    assert result == {
        "ok": True,
        "result": make_evidence_result().model_dump(mode="json"),
    }


@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param(
            {
                "requirements": [],
                "sections": VALID_EVIDENCE_SECTIONS,
            },
            id="empty-requirements",
        ),
        pytest.param(
            {
                "requirements": VALID_EVIDENCE_REQUIREMENTS,
                "sections": [],
            },
            id="empty-sections",
        ),
        pytest.param(
            {
                "requirements": VALID_EVIDENCE_REQUIREMENTS,
                "sections": VALID_EVIDENCE_SECTIONS,
                "max_evidence_per_requirement": 1,
            },
            id="backend-controlled-limit",
        ),
    ],
)
def test_search_resume_evidence_rejects_invalid_arguments(
    monkeypatch,
    arguments: dict,
):
    calls: list[tuple[list[str], list[ResumeSection]]] = []

    def fake_search_resume_evidence(
        requirements: list[str],
        sections: list[ResumeSection],
    ) -> EvidenceSearchResult:
        calls.append((requirements, sections))
        return make_evidence_result()

    monkeypatch.setattr(
        jobfit,
        "search_resume_evidence",
        fake_search_resume_evidence,
    )

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="search_resume_evidence",
            arguments=arguments,
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具参数校验失败",
    }
    assert calls == []



def make_match_assessment_result() -> MatchAssessmentResult:
    return MatchAssessmentResult(
        assessments=[
            RequirementAssessment(
                requirement="熟悉 Python",
                status="partial_match",
                reason="存在最高分为 0.500 的原文证据，但未达到强匹配阈值 0.6。",
                evidence=make_evidence_result().matches[0].evidence,
            )
        ],
        summary=MatchSummary(
            strong_match_count=0,
            partial_match_count=1,
            insufficient_evidence_count=0,
        ),
    )


def test_assess_requirement_match_definition_has_expected_schema():
    registry = jobfit.build_jobfit_tool_registry()

    definitions = registry.openai_definitions()
    definition = next(
        item
        for item in definitions
        if item["function"]["name"] == "assess_requirement_match"
    )
    function = definition["function"]
    parameters = function["parameters"]

    assert "岗位要求" in function["description"]
    assert "原文证据" in function["description"]
    assert "strong_match" in function["description"]
    assert "partial_match" in function["description"]
    assert "insufficient_evidence" in function["description"]
    assert parameters["type"] == "object"
    assert "requirements" in parameters["properties"]
    assert "matches" in parameters["properties"]
    assert parameters["required"] == ["requirements", "matches"]
    assert parameters["additionalProperties"] is False


def test_assess_requirement_match_calls_existing_service(monkeypatch):
    calls: list[EvidenceSearchResult] = []

    def fake_assess_requirement_match(
        search_result: EvidenceSearchResult,
    ) -> MatchAssessmentResult:
        calls.append(search_result)
        return make_match_assessment_result()

    monkeypatch.setattr(
        jobfit,
        "assess_requirement_match",
        fake_assess_requirement_match,
    )

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="assess_requirement_match",
            arguments=make_evidence_result().model_dump(mode="json"),
            context=make_context(),
        )
    )

    assert calls == [make_evidence_result()]
    assert result == {
        "ok": True,
        "result": make_match_assessment_result().model_dump(mode="json"),
    }


@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param(
            {
                "requirements": VALID_EVIDENCE_REQUIREMENTS,
                "matches": [],
            },
            id="empty-matches",
        ),
        pytest.param(
            {
                **make_evidence_result().model_dump(mode="json"),
                "user_id": 999,
            },
            id="extra-field",
        ),
    ],
)
def test_assess_requirement_match_rejects_invalid_arguments(
    monkeypatch,
    arguments: dict,
):
    calls: list[EvidenceSearchResult] = []

    def fake_assess_requirement_match(
        search_result: EvidenceSearchResult,
    ) -> MatchAssessmentResult:
        calls.append(search_result)
        return make_match_assessment_result()

    monkeypatch.setattr(
        jobfit,
        "assess_requirement_match",
        fake_assess_requirement_match,
    )

    result = asyncio.run(
        execute_tool(
            registry=jobfit.build_jobfit_tool_registry(),
            tool_name="assess_requirement_match",
            arguments=arguments,
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具参数校验失败",
    }
    assert calls == []
