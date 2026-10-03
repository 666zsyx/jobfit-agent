# 汇总已完成任务的 Token Usage 和估算成本。

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.event_loop import configure_event_loop_policy
from app.db.models import AnalysisTask
from app.db.session import async_session_factory, dispose_engine

configure_event_loop_policy()

REPORT_JSON_PATH = PROJECT_ROOT / "docs/agent_cost_results.json"
REPORT_MARKDOWN_PATH = PROJECT_ROOT / "docs/COST_REPORT.md"


def combine_usage_by_model(
    metrics_list: list[dict],
) -> dict[str, dict]:
    combined: dict[str, dict] = {}
    for metrics in metrics_list:
        for model, usage in (metrics.get("usage_by_model") or {}).items():
            aggregate = combined.setdefault(
                model,
                {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost": 0.0,
                },
            )
            aggregate["calls"] += int(usage.get("calls", 0))
            aggregate["prompt_tokens"] += int(
                usage.get("prompt_tokens", 0)
            )
            aggregate["completion_tokens"] += int(
                usage.get("completion_tokens", 0)
            )
            aggregate["total_tokens"] += int(
                usage.get("total_tokens", 0)
            )
            aggregate["estimated_cost"] += float(
                usage.get("estimated_cost", 0.0)
            )
    return combined


def build_markdown_report(report: dict) -> str:
    lines = [
        "# STEP 12 Agent Cost Report",
        "",
        f"- Tasks: {report['task_count']}",
        f"- Currency: {report['currency']}",
        f"- Estimated cost: {report['estimated_cost']:.8f}",
        f"- Total tokens: {report['total_tokens']}",
        f"- Model calls: {report['calls']}",
        "",
        "## By Model",
        "",
    ]
    if not report["by_model"]:
        lines.append("- No cost records yet.")
    else:
        for model, usage in report["by_model"].items():
            lines.append(
                "- "
                f"{model}: calls={usage['calls']}, "
                f"total_tokens={usage['total_tokens']}, "
                f"estimated_cost={usage['estimated_cost']:.8f}"
            )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- 价格由 LLM_INPUT_PRICE_PER_1M / LLM_OUTPUT_PRICE_PER_1M 配置。",
            "- 未配置价格时成本为 0，不猜测供应商价格。",
            "- metrics_json 缺失的历史任务不计入成本汇总。",
        ]
    )
    return "\n".join(lines) + "\n"


async def build_cost_report() -> dict:
    limit = int(os.getenv("COST_REPORT_LIMIT", "1000"))
    async with async_session_factory() as session:
        statement = (
            select(AnalysisTask)
            .where(
                AnalysisTask.deleted_at.is_(None),
                AnalysisTask.metrics_json.is_not(None),
            )
            .order_by(AnalysisTask.created_at.desc())
            .limit(limit)
        )
        tasks = list((await session.scalars(statement)).all())

    metrics_list = [
        task.metrics_json or {}
        for task in tasks
    ]
    by_model = combine_usage_by_model(metrics_list)
    return {
        "task_count": len(tasks),
        "currency": next(
            (
                metrics.get("currency", "USD")
                for metrics in metrics_list
                if metrics.get("currency")
            ),
            "USD",
        ),
        "calls": sum(
            int(metrics.get("usage_call_count", 0))
            for metrics in metrics_list
        ),
        "prompt_tokens": sum(
            int((metrics.get("usage") or {}).get("prompt_tokens", 0))
            for metrics in metrics_list
        ),
        "completion_tokens": sum(
            int(
                (metrics.get("usage") or {}).get(
                    "completion_tokens",
                    0,
                )
            )
            for metrics in metrics_list
        ),
        "total_tokens": sum(
            int((metrics.get("usage") or {}).get("total_tokens", 0))
            for metrics in metrics_list
        ),
        "estimated_cost": round(
            sum(
                float(metrics.get("estimated_cost", 0.0))
                for metrics in metrics_list
            ),
            8,
        ),
        "by_model": by_model,
    }


async def main() -> None:
    try:
        report = await build_cost_report()
        REPORT_JSON_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        REPORT_MARKDOWN_PATH.write_text(
            build_markdown_report(report),
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
