# 用持久化 RAG 主链路真实执行 Agent 评估，并生成独立报告。
#
# 与 evaluate_agent_live.py 的区别：
# - 这里先为每条 case 建立简历版本、Chunk 和向量索引；
# - search_resume_evidence 走 BM25 + 向量 + RRF + Rerank；
# - 因此 citation_ids 和三态分数来自主 RAG 链路，而不是关键词回退。

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from evaluate_agent_live import (
    build_markdown_report,
    derive_observed_outcome,
    git_revision,
    score_live_observations,
    utc_now,
)

from app.db.models import KnowledgeChunk, Resume, ResumeVersion, User
from app.db.session import async_session_factory, dispose_engine
from app.schemas.auth import CurrentUser
from app.services.agent_evaluation import AgentEvaluationCase
from app.services.rag_evidence import prepare_resume_rag
from app.services.rag_runtime import get_vector_index
from app.services.react_agent import (
    JOBFIT_PERSISTED_SYSTEM_PROMPT,
    build_jobfit_react_messages,
    run_react_loop,
)
from app.tools import ToolContext
from app.tools.jobfit import build_jobfit_tool_registry

DATASET_PATH = PROJECT_ROOT / "data/evaluation/agent_cases.json"
OBSERVATIONS_PATH = (
    PROJECT_ROOT / "data/evaluation/agent_live_persisted_observations.json"
)
REPORT_JSON_PATH = (
    PROJECT_ROOT / "docs/agent_evaluation_persisted_live_results.json"
)
REPORT_MARKDOWN_PATH = (
    PROJECT_ROOT / "docs/AGENT_EVALUATION_PERSISTED_LIVE.md"
)

CONTRACT_ONLY_CASE_IDS = {
    "confirmation_revise_recovered",
    "user_reject_cancelled",
    "max_steps_interrupted",
}
MOCK_ONLY_CASE_IDS = {
    "mock_max_steps_loop",
    "mock_repeated_tool_loop",
}


def load_cases() -> list[AgentEvaluationCase]:
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    return [
        AgentEvaluationCase.model_validate(item)
        for item in payload["cases"]
    ]


def skip_reason(case: AgentEvaluationCase) -> str | None:
    if case.case_id in CONTRACT_ONLY_CASE_IDS:
        return "需要持久化人工确认/中断契约测试，不在本 runner 范围"
    if case.case_id in MOCK_ONLY_CASE_IDS:
        return "mock-only 循环 case，不在持久化 RAG runner 范围"
    return None


async def seed_case(case: AgentEvaluationCase) -> tuple[int, int, int]:
    suffix = uuid4().hex[:12]
    username = f"persisted-live-{suffix}"
    sections = {
        "sections": [
            {
                "section_type": "project_experience",
                "title": "简历原文",
                "content": case.resume_text,
            }
        ]
    }

    async with async_session_factory() as session, session.begin():
        user = User(
            username=username,
            email=f"{username}@example.com",
            role="user",
            status="active",
        )
        session.add(user)
        await session.flush()

        resume = Resume(
            user_id=user.user_id,
            title="Persisted RAG Live Evaluation",
            status="active",
        )
        session.add(resume)
        await session.flush()

        version = ResumeVersion(
            resume_id=resume.resume_id,
            version_no=1,
            raw_text=case.resume_text,
            extracted_sections=sections,
            source_type="text",
        )
        session.add(version)
        await session.flush()

        await prepare_resume_rag(
            session,
            user_id=user.user_id,
            resume_version_id=version.resume_version_id,
        )
        return user.user_id, resume.resume_id, version.resume_version_id


async def cleanup_case(
    *,
    user_id: int,
    resume_id: int,
    resume_version_id: int,
) -> None:
    try:
        get_vector_index().delete_resume_version(
            user_id=user_id,
            resume_version_id=resume_version_id,
        )
    except Exception:
        logger.warning(
            "清理向量索引失败 user_id=%s",
            user_id,
            exc_info=True,
        )

    async with async_session_factory() as session, session.begin():
        await session.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.user_id == user_id
            )
        )
        await session.execute(
            delete(ResumeVersion).where(
                ResumeVersion.resume_id == resume_id
            )
        )
        await session.execute(
            delete(Resume).where(Resume.resume_id == resume_id)
        )
        await session.execute(
            delete(User).where(User.user_id == user_id)
        )


async def run_case(
    case: AgentEvaluationCase,
    *,
    max_steps: int,
) -> tuple[dict, dict]:
    user_id, resume_id, resume_version_id = await seed_case(case)
    try:
        snapshot = {
            "found": True,
            "task_id": 1,
            "resume_id": resume_id,
            "resume_version_id": resume_version_id,
            "version_no": 1,
            "resume_title": "Persisted RAG Live Evaluation",
            "extracted_sections": {
                "sections": [
                    {
                        "section_type": "project_experience",
                        "title": "简历原文",
                        "content": case.resume_text,
                    }
                ]
            },
        }
        context = ToolContext(
            current_user=CurrentUser(
                id=user_id,
                username=f"persisted-live-{user_id}",
                role="user",
            ),
            session_factory=async_session_factory,
            task_id=1,
            resume_profile_snapshot=snapshot,
            resume_version_id=resume_version_id,
            rag_enabled=True,
            defer_report_save=True,
        )
        result = await run_react_loop(
            messages=build_jobfit_react_messages(
                job_description=case.job_description,
                resume_text=None,
                system_prompt=JOBFIT_PERSISTED_SYSTEM_PROMPT,
            ),
            registry=build_jobfit_tool_registry(),
            context=context,
            max_steps=max_steps,
        )
        observed, extras = derive_observed_outcome(result)
        return observed.model_dump(mode="json"), extras
    finally:
        await cleanup_case(
            user_id=user_id,
            resume_id=resume_id,
            resume_version_id=resume_version_id,
        )


async def execute(
    cases: list[AgentEvaluationCase],
    *,
    max_steps: int,
    limit: int,
) -> dict:
    executed: list[dict] = []
    skipped: list[dict] = []

    runnable = [case for case in cases if skip_reason(case) is None]
    if limit > 0:
        runnable = runnable[:limit]

    for index, case in enumerate(runnable, start=1):
        print(
            f"[{index}/{len(runnable)}] persisted live run: {case.case_id}",
            flush=True,
        )
        try:
            observed, extras = await run_case(
                case,
                max_steps=max_steps,
            )
        except Exception as exc:  # noqa: BLE001
            skipped.append(
                {
                    "case_id": case.case_id,
                    "category": case.category,
                    "skip_reason": f"持久化 RAG 执行失败: {exc}",
                }
            )
            print(f"    FAILED: {exc}", flush=True)
            continue

        executed.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "observed": observed,
                "extras": extras,
            }
        )
        print(
            "    status="
            f"{observed.get('task_status')} "
            f"tools={len(observed.get('tools', []))} "
            f"steps={observed.get('steps')} "
            f"tokens={observed.get('usage_total')} "
            f"latency={observed.get('latency_ms')}ms",
            flush=True,
        )

    for case in cases:
        reason = skip_reason(case)
        if reason is not None:
            skipped.append(
                {
                    "case_id": case.case_id,
                    "category": case.category,
                    "skip_reason": reason,
                }
            )

    return {
        "version": 1,
        "source": "live_persisted_rag",
        "entrypoint": "app.services.react_agent.run_react_loop",
        "generated_at": utc_now(),
        "git_revision": git_revision(),
        "model": None,
        "max_steps": max_steps,
        "dataset": str(DATASET_PATH.relative_to(PROJECT_ROOT)),
        "executed_cases": executed,
        "skipped_cases": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用持久化 RAG 主链路真实执行 Agent 评估",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument(
        "--case-ids",
        nargs="*",
        default=None,
        help="只跑指定 case_id（可选）",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cases = load_cases()
    if args.case_ids:
        wanted = set(args.case_ids)
        cases = [case for case in cases if case.case_id in wanted]
    if not cases:
        raise SystemExit("没有匹配的 case")

    if args.dry_run:
        for case in cases:
            reason = skip_reason(case)
            state = "SKIP" if reason else "RUN "
            print(f"{state} {case.case_id} ({case.category}) {reason or ''}")
        return

    async def run_and_dispose() -> dict:
        try:
            return await execute(
                cases,
                max_steps=args.max_steps,
                limit=args.limit,
            )
        finally:
            await dispose_engine()

    observations = asyncio.run(run_and_dispose())
    if not observations["executed_cases"]:
        print("没有成功执行的 case，未生成报告。", file=sys.stderr)
        raise SystemExit(2)

    OBSERVATIONS_PATH.write_text(
        json.dumps(observations, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report, _, _ = score_live_observations(cases, observations)
    REPORT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    REPORT_MARKDOWN_PATH.write_text(
        build_markdown_report(report),
        encoding="utf-8",
    )


    print(f"observations={OBSERVATIONS_PATH}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"strict_passed={report['strict_passed']}")
    print(f"json_report={REPORT_JSON_PATH}")
    print(f"markdown_report={REPORT_MARKDOWN_PATH}")


if __name__ == "__main__":
    main()
