# 幂等创建本地演示用户、简历和岗位数据。

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.db.models import Resume, User
from app.db.session import async_session_factory, dispose_engine
from app.repositories import (
    JobRepository,
    ResumeRepository,
    UserRepository,
)
from app.services.resume_file_parser import ResumeParseResult
from app.services.resume_ingestion import persist_parsed_resume


DEMO_RESUME_TITLE = "演示简历：Python Agent 开发"
DEMO_JOB_TITLE = "Python AI Agent 开发工程师（演示）"
DEMO_JOB_COMPANY = "JobFit 示例科技"


def build_demo_resume_text() -> str:
    return """张三
求职方向：Python / AI Agent 开发

个人总结
具备 Python 后端与 AI Agent 应用开发经验，熟悉 FastAPI、异步任务、RAG 检索和工具调用。能够独立完成从接口设计、数据持久化到测试和部署配置的完整链路。

专业技能
Python、FastAPI、SQLAlchemy、PostgreSQL、Redis、Pydantic、pytest。
熟悉 LLM API、Prompt Engineering、结构化输出、Function Calling、ReAct 和 LangGraph。
掌握文本 Chunking、Embedding、BM25、向量检索、RRF 和 Cross-Encoder Rerank。
了解 Docker、Linux、Git、REST API 和 SSE。

项目经历
JobFit Agent：设计和实现岗位匹配分析 Agent 后端。
- 使用 FastAPI 构建简历、岗位和分析任务 API。
- 手写 ReAct 主循环，并使用 LangGraph 重构为可持久化状态图。
- 使用 PostgreSQL 保存任务、报告和 Checkpoint，支持人工确认与中断恢复。
- 构建 PostgreSQL + FastEmbed + Chroma RAG 链路，完成混合检索、Rerank 和 chunk_id 引用校验。
- 增加 Agent 评估、请求限流、Prompt Injection 防护、结构化日志和 Token 成本统计。

教育经历
合肥工业大学，信息安全，本科，2023.09-2027.06。
"""


def build_demo_extracted_sections() -> dict:
    return {
        "sections": [
            {
                "section_type": "summary",
                "title": "个人总结",
                "content": (
                    "具备 Python 后端与 AI Agent 应用开发经验，熟悉 "
                    "FastAPI、异步任务、RAG 检索和工具调用。"
                ),
            },
            {
                "section_type": "skills",
                "title": "专业技能",
                "content": (
                    "Python、FastAPI、SQLAlchemy、PostgreSQL、Redis、"
                    "Pydantic、pytest、LLM API、Prompt Engineering、"
                    "Function Calling、ReAct、LangGraph、Embedding、"
                    "BM25、向量检索、RRF、Rerank、Docker、Linux、Git。"
                ),
            },
            {
                "section_type": "project_experience",
                "title": "JobFit Agent 项目",
                "content": (
                    "使用 FastAPI 构建岗位匹配 Agent 后端；手写 ReAct "
                    "并使用 LangGraph 重构；使用 PostgreSQL Checkpoint "
                    "支持人工确认和中断恢复；构建 FastEmbed + Chroma "
                    "混合检索与 Rerank 链路，并完成引用校验、评估、"
                    "限流、成本统计和结构化日志。"
                ),
            },
            {
                "section_type": "education",
                "title": "教育经历",
                "content": "合肥工业大学，信息安全，本科，2023.09-2027.06。",
            },
        ]
    }


def build_demo_job_description() -> str:
    return """岗位职责
1. 参与 Python AI Agent 应用开发，完成后端接口、工具调用和状态编排。
2. 参与 RAG 知识库建设，包括文本切分、Embedding、向量检索和 Rerank。
3. 使用 LangGraph 或类似工作流框架实现多步骤任务、人工确认和失败恢复。
4. 参与工程化建设，包括结构化日志、测试、成本统计和接口文档。
5. 与产品和业务协作，将需求拆解为可测试、可追踪的后端任务。

任职要求
1. 熟悉 Python，掌握 FastAPI 或同类 Web 框架。
2. 熟悉 PostgreSQL 和 Redis，有异步编程经验。
3. 理解 LLM 基础调用、Prompt、结构化输出和 Function Calling。
4. 有 RAG、Agent 或 LangGraph 项目经验优先。
5. 具备良好的 Git、测试和问题排查习惯。
"""


def build_demo_job_requirements() -> dict:
    return {
        "responsibilities": [
            "参与 Python AI Agent 应用开发",
            "参与 RAG 知识库建设",
            "使用 LangGraph 实现工作流、人工确认和失败恢复",
            "参与日志、测试和成本统计等工程化建设",
        ],
        "required_skills": [
            "熟悉 Python 和 FastAPI",
            "熟悉 PostgreSQL 和 Redis",
            "理解 LLM 调用、Prompt、结构化输出和 Function Calling",
        ],
        "nice_to_have": [
            "有 RAG、Agent 或 LangGraph 项目经验",
        ],
    }


def find_demo_resume(
    resumes: list[Resume],
) -> Resume | None:
    return next(
        (resume for resume in resumes if resume.title == DEMO_RESUME_TITLE),
        None,
    )


def find_demo_job(jobs: list) -> object | None:
    return next(
        (
            job
            for job in jobs
            if job.title == DEMO_JOB_TITLE
            and job.company_name == DEMO_JOB_COMPANY
        ),
        None,
    )


async def ensure_demo_user(session) -> tuple[User, bool]:
    repository = UserRepository(session)
    user = await repository.get_by_username(settings.demo_username)
    if user is not None:
        if user.status != "active":
            raise RuntimeError("演示用户已存在但状态不是 active")
        return user, False

    user = User(
        username=settings.demo_username,
        email="demo_user@example.com",
        role="admin",
        status="active",
    )
    session.add(user)
    await session.flush()
    return user, True


async def ensure_demo_resume(
    session,
    *,
    user_id: int,
) -> tuple[int, int, bool]:
    repository = ResumeRepository(session)
    resumes = await repository.list_for_user(
        user_id,
        with_versions=True,
    )
    resume = find_demo_resume(resumes)
    if resume is not None and resume.versions:
        return resume.resume_id, resume.versions[-1].resume_version_id, False

    parsed = ResumeParseResult(
        text=build_demo_resume_text(),
        source_type="text",
        original_filename="demo_resume.txt",
        char_count=len(build_demo_resume_text()),
    )
    result = await persist_parsed_resume(
        session,
        user_id=user_id,
        parsed=parsed,
        resume_id=resume.resume_id if resume is not None else None,
        title=DEMO_RESUME_TITLE,
        extracted_sections=build_demo_extracted_sections(),
    )
    return result.resume_id, result.resume_version_id, True


async def ensure_demo_job(
    session,
    *,
    user_id: int,
) -> tuple[int, bool]:
    repository = JobRepository(session)
    jobs = await repository.list_for_user(user_id)
    job = find_demo_job(jobs)
    if job is not None:
        return job.job_id, False

    job = await repository.create(
        user_id=user_id,
        raw_description=build_demo_job_description(),
        title=DEMO_JOB_TITLE,
        company_name=DEMO_JOB_COMPANY,
        extracted_requirements=build_demo_job_requirements(),
    )
    return job.job_id, True


async def seed_demo_data() -> dict:
    result: dict[str, object] = {}
    try:
        async with async_session_factory() as session:
            async with session.begin():
                user, user_created = await ensure_demo_user(session)
                resume_id, resume_version_id, resume_created = (
                    await ensure_demo_resume(
                        session,
                        user_id=user.user_id,
                    )
                )
                job_id, job_created = await ensure_demo_job(
                    session,
                    user_id=user.user_id,
                )
                result = {
                    "user_id": user.user_id,
                    "username": user.username,
                    "user_created": user_created,
                    "resume_id": resume_id,
                    "resume_version_id": resume_version_id,
                    "resume_created": resume_created,
                    "job_id": job_id,
                    "job_created": job_created,
                }
    finally:
        await dispose_engine()
    return result


if __name__ == "__main__":
    print(
        json.dumps(
            asyncio.run(seed_demo_data()),
            ensure_ascii=False,
            indent=2,
        )
    )
