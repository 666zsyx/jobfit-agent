# 验证持久化 Agent 的 Prompt 和可运行状态集合。

import asyncio

import pytest
from fakeredis.aioredis import FakeRedis

from app.services.persisted_agent import (
    RUNNABLE_TASK_STATUSES,
    _cache_run_status_safely,
)
from app.services.react_agent import (
    JOBFIT_PERSISTED_SYSTEM_PROMPT,
    JOBFIT_REACT_SYSTEM_PROMPT,
    build_jobfit_react_messages,
)


def test_persisted_prompt_mentions_all_tools_and_context_rules():
    prompt = JOBFIT_PERSISTED_SYSTEM_PROMPT

    for tool_name in (
        "get_resume_profile",
        "extract_job_requirements",
        "search_resume_evidence",
        "assess_requirement_match",
        "save_match_report",
    ):
        assert tool_name in prompt

    assert "user_id" in prompt
    assert "task_id" in prompt
    assert "后端提供" in prompt
    assert "chunk_id" in prompt


def test_build_messages_uses_persisted_prompt():
    messages = build_jobfit_react_messages(
        job_description="FastAPI 岗位",
        resume_text="Python 简历",
        system_prompt=JOBFIT_PERSISTED_SYSTEM_PROMPT,
    )

    assert messages[0]["role"] == "system"
    assert messages[0]["content"].startswith(JOBFIT_PERSISTED_SYSTEM_PROMPT)
    assert "安全的不可信数据" in messages[0]["content"]


def test_build_messages_keeps_original_prompt_by_default():
    messages = build_jobfit_react_messages(
        job_description="FastAPI 岗位",
        resume_text="Python 简历",
    )

    assert messages[0]["content"].startswith(JOBFIT_REACT_SYSTEM_PROMPT)
    assert "安全的不可信数据" in messages[0]["content"]


def test_only_pending_and_interrupted_tasks_are_runnable():
    assert RUNNABLE_TASK_STATUSES == {"pending", "interrupted"}

    for terminal_status in (
        "running",
        "completed",
        "failed",
        "cancelled",
    ):
        assert terminal_status not in RUNNABLE_TASK_STATUSES


def test_cache_helper_does_not_swallow_value_error():
    async def scenario():
        redis = FakeRedis(decode_responses=True)
        try:
            with pytest.raises(ValueError):
                await _cache_run_status_safely(
                    redis,
                    user_id=1,
                    task_id=10,
                    status="running",
                    current_step=0,
                    attempt=1,
                    max_steps=0,
                )
        finally:
            await redis.aclose()

    asyncio.run(scenario())


def test_keyword_prompt_requires_sections_before_evidence_search():
    prompt = JOBFIT_REACT_SYSTEM_PROMPT

    # 非持久化关键词流程必须先取得简历分段，再带 sections 检索证据。
    assert "sections" in prompt
    assert "禁止在未取得分段前调用它" in prompt
    assert prompt.index("第一步调用 extract_job_requirements") < prompt.index(
        "第二步调用 extract_resume_sections"
    )
    assert prompt.index("第二步调用 extract_resume_sections") < prompt.index(
        "第三步调用 search_resume_evidence"
    )
    # 该路径没有持久化上下文，必须明确禁止调用 get_resume_profile。
    assert "禁止调用 get_resume_profile" in prompt


def test_persisted_prompt_forbids_resume_section_extraction():
    prompt = JOBFIT_PERSISTED_SYSTEM_PROMPT

    assert "禁止调用 extract_resume_sections" in prompt
    assert "禁止调用 get_resume_profile" not in prompt
