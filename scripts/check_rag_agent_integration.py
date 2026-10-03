# 真实验证 RAG 准备、混合检索、Rerank、三态评估和引用链。

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import Resume, ResumeVersion, User
from app.db.session import async_session_factory, dispose_engine
from app.services.matching import assess_requirement_match
from app.services.rag_evidence import (
    prepare_resume_rag,
    search_requirements_with_rag,
)


async def check_rag_agent_integration() -> None:
    suffix = uuid4().hex[:12]

    async with async_session_factory() as session:
        transaction = await session.begin()

        owner = User(
            username=f"rag-agent-{suffix}",
            email=f"rag-agent-{suffix}@example.com",
        )
        session.add(owner)
        await session.flush()

        resume = Resume(user_id=owner.user_id, title="STEP08 RAG Agent")
        session.add(resume)
        await session.flush()

        version = ResumeVersion(
            resume_id=resume.resume_id,
            version_no=1,
            raw_text="STEP08 RAG Agent source",
            extracted_sections={
                "sections": [
                    {
                        "section_type": "skills",
                        "title": "技能",
                        "content": (
                            "Python、FastAPI、PostgreSQL 17、Redis，"
                            "熟悉后端接口开发和数据库设计。"
                        ),
                    },
                    {
                        "section_type": "project_experience",
                        "title": "课程平台",
                        "content": (
                            "使用 FastAPI 开发课程接口，"
                            "负责 API 设计、权限校验和联调。"
                        ),
                    },
                    {
                        "section_type": "work_experience",
                        "title": "实习经历",
                        "content": (
                            "参与第三方 API 对接和接口联调，"
                            "记录请求参数与返回结果。"
                        ),
                    },
                    {
                        "section_type": "other",
                        "title": "其他技能",
                        "content": "了解 Rust 和 C++，主要参加算法课程练习。",
                    },
                ]
            },
        )
        session.add(version)
        await session.flush()

        await prepare_resume_rag(
            session,
            user_id=owner.user_id,
            resume_version_id=version.resume_version_id,
        )

        requirements = [
            "熟悉 Python 和 FastAPI",
            "有后端接口开发经验",
            "熟悉 PostgreSQL 17",
        ]
        search_result, evidence_packs = (
            await search_requirements_with_rag(
                session,
                user_id=owner.user_id,
                resume_version_id=version.resume_version_id,
                requirements=requirements,
            )
        )
        assessment = assess_requirement_match(search_result)

        cited_chunk_ids = sorted(
            {
                item.chunk_id
                for pack in evidence_packs
                for item in pack.items
                if item.chunk_id is not None
            }
        )

        assert len(search_result.matches) == len(requirements)
        assert assessment.assessments
        assert any(
            item.status != "insufficient_evidence"
            for item in assessment.assessments
        )
        assert cited_chunk_ids

        print(f"requirements: {len(requirements)}")
        print(f"evidence packs: {len(evidence_packs)}")
        print(f"cited chunk ids: {cited_chunk_ids}")

        for item in assessment.assessments:
            print(
                f"status={item.status} "
                f"evidence_count={len(item.evidence)} "
                f"requirement={item.requirement}"
            )

        print("rag agent integration: ok")

        await transaction.rollback()

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(check_rag_agent_integration())
