# 验证演示种子数据的结构和幂等识别辅助逻辑。

from types import SimpleNamespace

from app.schemas.resume import ResumeExtraction
from scripts.seed_demo_data import (
    DEMO_JOB_COMPANY,
    DEMO_JOB_TITLE,
    DEMO_RESUME_TITLE,
    build_demo_extracted_sections,
    build_demo_job_description,
    build_demo_job_requirements,
    build_demo_resume_text,
    find_demo_job,
    find_demo_resume,
)


def test_demo_resume_text_has_required_sections():
    text = build_demo_resume_text()

    assert "个人总结" in text
    assert "专业技能" in text
    assert "JobFit Agent" in text
    assert "LangGraph" in text
    assert "Checkpoint" in text


def test_demo_resume_sections_match_schema():
    extraction = ResumeExtraction.model_validate(
        build_demo_extracted_sections()
    )

    assert extraction.sections[0].section_type == "summary"
    assert any(
        section.section_type == "project_experience"
        for section in extraction.sections
    )


def test_demo_job_description_and_requirements_are_useful():
    description = build_demo_job_description()
    requirements = build_demo_job_requirements()

    assert "Python AI Agent" in description
    assert "RAG" in description
    assert "LangGraph" in description
    assert requirements["responsibilities"]
    assert requirements["required_skills"]


def test_demo_resume_and_job_are_found_by_stable_markers():
    resume = SimpleNamespace(
        resume_id=11,
        title=DEMO_RESUME_TITLE,
        versions=[SimpleNamespace(resume_version_id=22)],
    )
    job = SimpleNamespace(
        job_id=33,
        title=DEMO_JOB_TITLE,
        company_name=DEMO_JOB_COMPANY,
    )

    assert find_demo_resume([resume]) is resume
    assert find_demo_job([job]) is job
