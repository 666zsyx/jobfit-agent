# 真实执行 JobFit ReAct Agent，采集观测值并生成不可回放的评估报告。

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.core.exceptions import LLMServiceError
from app.schemas.auth import CurrentUser
from app.schemas.react_agent import ReactAgentResult
from app.services.agent_evaluation import (
    AgentEvaluationCase,
    ObservedAgentOutcome,
    evaluate_agent_case,
    summarize_agent_results,
)
from app.services.react_agent import (
    DEFAULT_MAX_REACT_STEPS,
    run_jobfit_agent,
)
from app.tools import ToolContext

DATASET_PATH = PROJECT_ROOT / "data/evaluation/agent_cases.json"
OBSERVATIONS_PATH = PROJECT_ROOT / "data/evaluation/agent_live_observations.json"
REPORT_JSON_PATH = PROJECT_ROOT / "docs/agent_evaluation_live_results.json"
REPORT_MARKDOWN_PATH = PROJECT_ROOT / "docs/AGENT_EVALUATION_LIVE.md"
REPLAY_REPORT_PATH = PROJECT_ROOT / "docs/agent_evaluation_results.json"

MATCH_TOOL_NAME = "assess_requirement_match"

# 本脚本走非持久化关键词 ReAct 路径（等价 POST /api/agent/match）。
# 人工确认、拒绝和 Graph 中断需要持久化路径，这里显式跳过并如实报告。
SKIPPED_CATEGORIES = {"human_confirmation"}

# 真实运行状态到评估集状态词汇的映射。
LIVE_STATUS_MAP = {
    "completed": "completed",
    "max_steps_reached": "interrupted",
}

# 只对真实运行能覆盖的指标设门槛；人工确认恢复率在关键词路径不适用。
# 门槛用“必要工具覆盖率”而不是严格序列全等：关键词路径本来就需要
# extract_resume_sections 这类额外调用，严格全等会恒为 0。
LIVE_THRESHOLDS = {
    "task_completion_rate": (0.85, ">="),
    "tool_recall": (0.90, ">="),
    "tool_f1": (0.85, ">="),
    "tool_success_rate": (0.95, ">="),
    "match_status_f1": (0.85, ">="),
    "abstention_accuracy": (0.90, ">="),
    "unsupported_suggestion_rate": (0.15, "<="),
}

# evidence_backed_rate 不在回放基线里，单独设门槛。
LIVE_EVIDENCE_THRESHOLD = 0.85


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    revision = completed.stdout.strip()
    return revision or None


# 判断某个 case 能否由非持久化关键词 ReAct 路径真实覆盖。
def skip_reason(case: AgentEvaluationCase) -> str | None:
    if case.category in SKIPPED_CATEGORIES:
        return "需要持久化人工确认路径"
    if case.expected.task_status in {"cancelled", "interrupted"}:
        return "需要持久化任务状态或强制步数上限"
    return None


# 取出工具成功返回的业务载荷；失败调用统一返回空字典。
def tool_payload(execution) -> dict:
    raw = execution.result
    if not isinstance(raw, dict) or not raw.get("ok"):
        return {}
    payload = raw.get("result")
    return payload if isinstance(payload, dict) else {}


def last_tool_payload(result: ReactAgentResult, tool_name: str) -> dict:
    for execution in reversed(result.trace):
        if execution.tool_name != tool_name:
            continue
        payload = tool_payload(execution)
        if payload:
            return payload
    return {}


def _dedupe(values: list[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def collect_citation_ids(assessments: list[dict]) -> list[int]:
    citation_ids: list[int] = []
    for assessment in assessments:
        for evidence in assessment.get("evidence") or []:
            chunk_id = evidence.get("chunk_id")
            if isinstance(chunk_id, int):
                citation_ids.append(chunk_id)
    return _dedupe(citation_ids)


# 检查每条结论都有证据支撑：非 insufficient 必须有证据，insufficient 必须没有。
def evidence_backed(assessments: list[dict]) -> bool:
    if not assessments:
        return False

    for assessment in assessments:
        has_evidence = bool(assessment.get("evidence"))
        is_insufficient = (
            assessment.get("status") == "insufficient_evidence"
        )
        if is_insufficient == has_evidence:
            return False
    return True


def derive_observed_outcome(
    result: ReactAgentResult,
) -> tuple[ObservedAgentOutcome, dict]:
    """把一次真实 ReAct 运行转换成评估观测值。"""

    tools = [execution.tool_name for execution in result.trace]
    tool_error_count = sum(
        1 for execution in result.trace if not execution.result.get("ok")
    )

    match_payload = last_tool_payload(result, MATCH_TOOL_NAME)
    assessments = [
        item
        for item in (match_payload.get("assessments") or [])
        if isinstance(item, dict)
    ]
    match_statuses = [
        item.get("status")
        for item in assessments
        if item.get("status")
    ]
    citation_ids = collect_citation_ids(assessments)

    suggestion_count = len(assessments)
    unsupported_suggestion_count = sum(
        1
        for item in assessments
        if item.get("status") != "insufficient_evidence"
        and not (item.get("evidence") or [])
    )

    abstained = bool(match_statuses) and all(
        status == "insufficient_evidence" for status in match_statuses
    )

    task_status = LIVE_STATUS_MAP.get(result.status, "completed")
    error_code = (
        "max_steps_reached"
        if result.status == "max_steps_reached"
        else None
    )

    observed = ObservedAgentOutcome(
        task_status=task_status,
        tools=tools,
        match_statuses=match_statuses,
        citation_ids=citation_ids,
        abstained=abstained,
        # 关键词路径不经过人工确认，该指标不参与 live 门槛。
        confirmation_recovered=True,
        tool_call_count=len(result.trace),
        tool_error_count=tool_error_count,
        suggestion_count=suggestion_count,
        unsupported_suggestion_count=unsupported_suggestion_count,
        steps=result.steps,
        usage_total=result.usage.total_tokens,
        latency_ms=result.latency_ms,
        error_code=error_code,
    )

    evidence_item_count = sum(
        len(item.get("evidence") or []) for item in assessments
    )
    extras = {
        "assessment_count": len(assessments),
        "evidence_item_count": evidence_item_count,
        "evidence_backed": evidence_backed(assessments),
        "assessments": assessments,
        "tool_calls": [
            {
                "tool_name": execution.tool_name,
                "step": execution.step,
                "ok": bool(execution.result.get("ok")),
                "error": execution.result.get("error"),
            }
            for execution in result.trace
        ],
    }
    return observed, extras


async def run_live_case(
    case: AgentEvaluationCase,
    *,
    max_steps: int,
) -> tuple[ObservedAgentOutcome, dict]:
    """真实调用 LLM 和工具执行一次 case，不做任何 mock。"""

    context = ToolContext(
        current_user=CurrentUser(
            id=1,
            username="live-evaluation",
            role="demo",
        )
    )
    result = await run_jobfit_agent(
        job_description=case.job_description,
        resume_text=case.resume_text,
        context=context,
        max_steps=max_steps,
    )
    return derive_observed_outcome(result)


def load_dataset(path: Path = DATASET_PATH) -> list[AgentEvaluationCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        AgentEvaluationCase.model_validate(item)
        for item in payload["cases"]
    ]


def compare_metric(value: float, threshold: float, operator: str) -> bool:
    if operator == ">=":
        return value >= threshold
    if operator == "<=":
        return value <= threshold
    raise ValueError(f"未知比较符：{operator}")


def threshold_results(summary, thresholds: dict) -> dict:
    values = summary.model_dump()
    results: dict = {}
    for name, (threshold, operator) in thresholds.items():
        value = float(values[name])
        results[name] = {
            "value": value,
            "threshold": threshold,
            "operator": operator,
            "passed": compare_metric(value, threshold, operator),
        }
    return results


# 把真实运行结果落盘，便于离线复算和现场复现。
def build_observations_payload(
    *,
    executed: list[dict],
    skipped: list[dict],
    max_steps: int,
) -> dict:
    return {
        "version": 1,
        "source": "live_react_keyword",
        "entrypoint": "app.services.react_agent.run_jobfit_agent",
        "generated_at": utc_now(),
        "git_revision": git_revision(),
        "model": settings.llm_model,
        "llm_base_url": settings.llm_base_url,
        "max_steps": max_steps,
        "dataset": str(DATASET_PATH.relative_to(PROJECT_ROOT)),
        "executed_cases": executed,
        "skipped_cases": skipped,
    }


def load_observations(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# 用真实观测值替换数据集里的回放观测值，复用同一套评分逻辑。
def summarize_by_category(case_details: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}
    for case in case_details:
        grouped.setdefault(case["category"], []).append(case)

    result: dict[str, dict] = {}
    for category, cases in sorted(grouped.items()):
        metrics = [case["metrics"] for case in cases]
        count = len(metrics)
        result[category] = {
            "case_count": count,
            "task_completion_rate": sum(
                1 for item in metrics if item["task_completed"]
            ) / count,
            "tool_f1": sum(item["tool_f1"] for item in metrics) / count,
            "tool_success_rate": sum(
                item["tool_success_rate"] for item in metrics
            ) / count,
            "match_status_f1": sum(
                item["match_status_f1"] for item in metrics
            ) / count,
            "citation_validity_rate": sum(
                1 for item in metrics if item["citation_valid"]
            ) / count,
            "abstention_accuracy": sum(
                1 for item in metrics if item["abstention_correct"]
            ) / count,
            "unsupported_suggestion_rate": sum(
                item["unsupported_suggestion_rate"] for item in metrics
            ) / count,
            "evidence_backed_rate": sum(
                1 for case in cases
                if case["extras"].get("evidence_backed")
            ) / count,
        }
    return result


def score_live_observations(
    cases: list[AgentEvaluationCase],
    observations: dict,
) -> tuple[dict, object, list[AgentEvaluationCase]]:
    executed = observations.get("executed_cases", [])
    observed_by_id = {
        item["case_id"]: item for item in executed
    }
    extras_by_id = {
        item["case_id"]: item.get("extras", {}) for item in executed
    }

    live_cases: list[AgentEvaluationCase] = []
    case_details: list[dict] = []

    for case in cases:
        record = observed_by_id.get(case.case_id)
        if record is None:
            continue

        live_case = AgentEvaluationCase(
            case_id=case.case_id,
            category=case.category,
            job_description=case.job_description,
            resume_text=case.resume_text,
            expected=case.expected,
            observed=ObservedAgentOutcome.model_validate(record["observed"]),
        )
        result = evaluate_agent_case(live_case)
        metrics = result.metrics.model_dump()
        metrics["evidence_backed"] = bool(
            extras_by_id.get(case.case_id, {}).get("evidence_backed")
        )
        case_details.append(
            {
                "case_id": live_case.case_id,
                "category": live_case.category,
                "metrics": metrics,
                "observed": live_case.observed.model_dump(mode="json"),
                "extras": extras_by_id.get(case.case_id, {}),
            }
        )
        live_cases.append(live_case)

    by_category = summarize_by_category(case_details)

    if not live_cases:
        raise ValueError("没有可评分的真实观测值")

    results = [evaluate_agent_case(case) for case in live_cases]
    summary = summarize_agent_results(
        results,
        observed_outcomes=[case.observed for case in live_cases],
    )

    thresholds = threshold_results(summary, LIVE_THRESHOLDS)
    evidence_backed_rate = (
        sum(1 for item in case_details if item["metrics"]["evidence_backed"])
        / len(case_details)
    )
    thresholds["evidence_backed_rate"] = {
        "value": evidence_backed_rate,
        "threshold": LIVE_EVIDENCE_THRESHOLD,
        "operator": ">=",
        "passed": evidence_backed_rate >= LIVE_EVIDENCE_THRESHOLD,
    }

    summary_payload = summary.model_dump(mode="json")
    summary_payload["evidence_backed_rate"] = evidence_backed_rate

    report = {
        "version": 1,
        "source": "live_react_keyword",
        "generated_at": observations.get("generated_at"),
        "git_revision": observations.get("git_revision"),
        "model": observations.get("model"),
        "max_steps": observations.get("max_steps"),
        "dataset_case_count": len(cases),
        "executed_case_count": len(case_details),
        "skipped_case_count": len(observations.get("skipped_cases", [])),
        "pending_case_count": max(
            0,
            len(cases)
            - len(case_details)
            - len(observations.get("skipped_cases", [])),
        ),
        "summary": summary_payload,
        "thresholds": thresholds,
        "strict_passed": all(
            item["passed"] for item in thresholds.values()
        ),
        "cases": case_details,
        "by_category": by_category,
        "skipped_cases": observations.get("skipped_cases", []),
    }
    return report, summary, live_cases


def load_replay_summary() -> dict | None:
    if not REPLAY_REPORT_PATH.exists():
        return None
    try:
        payload = json.loads(REPLAY_REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else None


def build_markdown_report(report: dict) -> str:
    summary = report["summary"]
    total = report.get(
        "dataset_case_count",
        report["executed_case_count"] + report["skipped_case_count"],
    )
    pending = report.get("pending_case_count", 0)
    lines = [
        "# Agent 评估（真实执行）",
        "",
        "本报告由 scripts/evaluate_agent_live.py 真实调用 LLM 和工具生成，",
        "不是回放固定观测值。",
        "",
        f"- 生成时间: {report.get('generated_at')}",
        f"- 模型: {report.get('model')}",
        f"- commit: {report.get('git_revision')}",
        f"- max_steps: {report.get('max_steps')}",
        (
            f"- 实际执行: {report['executed_case_count']} / {total} 个 case"
            + (
                f"（{pending} 条新增 case 尚无观测值）"
                if pending
                else ""
            )
        ),
        f"- 门槛结论: {'PASS' if report['strict_passed'] else 'REVIEW'}",
        "",
        "## 实测指标",
        "",
        f"- 任务完成率: {summary['task_completion_rate']:.4f}",
        f"- 必要工具覆盖率: {summary['tool_recall']:.4f}",
        f"- 工具精度: {summary['tool_precision']:.4f}",
        (
            f"- 工具序列(严格全等，仅供参考): "
            f"{summary['tool_sequence_accuracy']:.4f}"
        ),
        f"- 工具 F1: {summary['tool_f1']:.4f}",
        f"- 工具成功率: {summary['tool_success_rate']:.4f}",
        f"- 匹配状态 F1: {summary['match_status_f1']:.4f}",
        f"- 弃答准确率: {summary['abstention_accuracy']:.4f}",
        f"- 无依据建议比例: {summary['unsupported_suggestion_rate']:.4f}",
        f"- 证据支撑率: {summary['evidence_backed_rate']:.4f}",
        f"- 平均步数: {summary['average_steps']:.2f}",
        f"- 平均 Token: {summary['average_usage_total']:.2f}",
        f"- p50 延迟 ms: {summary['p50_latency_ms']:.2f}",
        f"- p95 延迟 ms: {summary['p95_latency_ms']:.2f}",
        "",
        "## 门槛",
        "",
        "| 指标 | 实测值 | 条件 | 结果 |",
        "|---|---:|---|---|",
    ]

    for name, item in report["thresholds"].items():
        lines.append(
            "| "
            f"{name} | {item['value']:.4f} | "
            f"{item['operator']} {item['threshold']:.4f} | "
            f"{'PASS' if item['passed'] else 'FAIL'} |"
        )

    lines.extend(["", "## 与回放基线对比", ""])
    replay = load_replay_summary()
    if replay is None:
        lines.append("- 未找到回放基线报告，跳过对比。")
    else:
        lines.extend(
            [
                "| 指标 | 回放基线 | 真实执行 |",
                "|---|---:|---:|",
            ]
        )
        for name in (
            "task_completion_rate",
            "tool_sequence_accuracy",
            "tool_precision",
            "tool_recall",
            "tool_f1",
            "tool_success_rate",
            "match_status_f1",
            "abstention_accuracy",
            "unsupported_suggestion_rate",
            "average_steps",
            "average_usage_total",
            "p50_latency_ms",
            "p95_latency_ms",
        ):
            before = replay.get(name)
            after = summary.get(name)
            if before is None or after is None:
                continue
            lines.append(
                f"| {name} | {float(before):.4f} | {float(after):.4f} |"
            )
        lines.extend(
            [
                "",
                "- 回放基线的 observed 字段是数据集里写死的常量。",
                "- 本报告耗时和 Token 来自真实模型调用，会有波动。",
            ]
        )

    lines.extend(["", "## 按类别", ""])
    lines.extend(
        [
            "| 类别 | case 数 | 任务完成 | 工具F1 | 匹配F1 | 弃答 | 证据支撑 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for category, item in report.get("by_category", {}).items():
        lines.append(
            f"| {category} | {item['case_count']} | "
            f"{item['task_completion_rate']:.4f} | "
            f"{item['tool_f1']:.4f} | "
            f"{item['match_status_f1']:.4f} | "
            f"{item['abstention_accuracy']:.4f} | "
            f"{item['evidence_backed_rate']:.4f} |"
        )

    lines.extend(
        [
            "",
            "## 逐条结果",
            "",
            "| case | 类别 | 完成 | 工具F1 | 弃答 | 证据支撑 | 步数 | Token | 延迟ms |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in report["cases"]:
        metrics = item["metrics"]
        observed = item["observed"]
        lines.append(
            f"| {item['case_id']} | {item['category']} | "
            f"{'Y' if metrics['task_completed'] else 'N'} | "
            f"{metrics['tool_f1']:.4f} | "
            f"{'Y' if metrics['abstention_correct'] else 'N'} | "
            f"{'Y' if metrics['evidence_backed'] else 'N'} | "
            f"{observed['steps']} | {observed['usage_total']} | "
            f"{observed['latency_ms']} |"
        )

    skipped = report.get("skipped_cases", [])
    lines.extend(["", "## 未覆盖 case", ""])
    if not skipped:
        lines.append("- 无。")
    else:
        for item in skipped:
            lines.append(
                f"- {item['case_id']}（{item['category']}）: "
                f"{item['skip_reason']}"
            )
    if pending:
        lines.append(
            f"- 另有 {pending} 条 case 尚无观测值（新增 live/mock case），"
            "需要下一次真实执行生成。"
        )

    lines.extend(
        [
            "",
            "## 说明",
            "",
            (
                "- tool_precision 会低于 1.0：当前 live 路径必须多调一次"
                " extract_resume_sections，而评估集的 expected.tools"
                " 只列了 4 个工具，这是 fixture 与路径的差异，不是多余调用。"
            ),
            "- 当前 live 路径不产生持久化 chunk_id，因此不计算引用 ID 维度的",
            "  citation_f1 / citation_validity_rate；引用质量由",
            "  evidence_backed_rate 和 unsupported_suggestion_rate 约束。",
            "- 人工确认恢复率在当前 live 路径不适用，未纳入本次门槛。",
            (
                "- tool_sequence_accuracy 是严格全等"
                "（工具名/顺序/数量完全一致），仅作参考；"
                "门槛用 tool_recall（必要工具覆盖率）衡量。"
            ),
            "- 需要 citation_ids 精确对比时，应把本脚本扩展到持久化 RAG 路径。",
        ]
    )
    return "\n".join(lines) + "\n"


async def execute_live(cases, *, max_steps: int, limit: int) -> dict:
    executed: list[dict] = []
    skipped: list[dict] = []
    attempted = 0

    for index, case in enumerate(cases, 1):
        reason = skip_reason(case)
        if reason is not None:
            skipped.append(
                {
                    "case_id": case.case_id,
                    "category": case.category,
                    "skip_reason": reason,
                }
            )
            continue

        if limit and attempted >= limit:
            skipped.append(
                {
                    "case_id": case.case_id,
                    "category": case.category,
                    "skip_reason": "超出 --limit 限制",
                }
            )
            continue

        attempted += 1
        print(f"[{index}/{len(cases)}] live run: {case.case_id}", flush=True)
        try:
            observed, extras = await run_live_case(
                case,
                max_steps=max_steps,
            )
        except LLMServiceError as exc:
            print(f"    LLM 失败: {exc}", flush=True)
            skipped.append(
                {
                    "case_id": case.case_id,
                    "category": case.category,
                    "skip_reason": f"LLM 调用失败: {exc}",
                }
            )
            continue

        print(
            f"    status={observed.task_status} tools={observed.tool_call_count} steps={observed.steps} tokens={observed.usage_total} latency={observed.latency_ms}ms",
            flush=True,
        )
        executed.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "observed": observed.model_dump(mode="json"),
                "extras": extras,
            }
        )

    return build_observations_payload(
        executed=executed,
        skipped=skipped,
        max_steps=max_steps,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="真实执行 JobFit Agent 并生成评估报告",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_REACT_STEPS,
    )
    parser.add_argument(
        "--from-observations",
        type=Path,
        default=None,
        help="不调用 LLM，直接用已保存的真实观测值复算报告",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cases = load_dataset()

    if args.dry_run:
        for case in cases:
            reason = skip_reason(case)
            state = "SKIP" if reason else "RUN "
            print(f"{state} {case.case_id} ({case.category}) {reason or ''}")
        return

    if args.from_observations is not None:
        observations = load_observations(args.from_observations)
    else:
        observations = asyncio.run(
            execute_live(
                cases,
                max_steps=args.max_steps,
                limit=args.limit,
            )
        )
        if not observations.get("executed_cases"):
            print(
                "没有成功执行的 case，未生成报告。请检查 LLM 网络与配置。",
                file=sys.stderr,
            )
            raise SystemExit(2)

        OBSERVATIONS_PATH.write_text(
            json.dumps(observations, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"observations={OBSERVATIONS_PATH}")

    if not observations.get("executed_cases"):
        print("观测文件中没有可评分的 case。", file=sys.stderr)
        raise SystemExit(2)

    report, _, _ = score_live_observations(cases, observations)

    REPORT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    REPORT_MARKDOWN_PATH.write_text(
        build_markdown_report(report),
        encoding="utf-8",
    )

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"strict_passed={report['strict_passed']}")
    print(f"json_report={REPORT_JSON_PATH}")
    print(f"markdown_report={REPORT_MARKDOWN_PATH}")

    if args.strict and not report["strict_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()