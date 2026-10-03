# 在固定数据集上评估 Agent 的完成度、工具、引用、安全和恢复指标。

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.agent_evaluation import (
    AgentEvaluationCase,
    AgentEvaluationSummary,
    evaluate_agent_case,
    summarize_agent_results,
)


DATASET_PATH = PROJECT_ROOT / "data/evaluation/agent_cases.json"
REPORT_JSON_PATH = PROJECT_ROOT / "docs/agent_evaluation_results.json"
REPORT_MARKDOWN_PATH = PROJECT_ROOT / "docs/AGENT_EVALUATION.md"


THRESHOLDS = {
    "task_completion_rate": (0.85, ">="),
    "tool_sequence_accuracy": (0.60, ">="),
    "tool_f1": (0.85, ">="),
    "tool_success_rate": (0.95, ">="),
    "match_status_f1": (0.85, ">="),
    "citation_f1": (0.80, ">="),
    "citation_validity_rate": (0.80, ">="),
    "abstention_accuracy": (0.90, ">="),
    "confirmation_recovery_rate": (0.95, ">="),
    "unsupported_suggestion_rate": (0.15, "<="),
}


def compare_metric(value: float, threshold: float, operator: str) -> bool:
    if operator == ">=":
        return value >= threshold
    if operator == "<=":
        return value <= threshold
    raise ValueError(f"未知比较符：{operator}")


def threshold_results(summary: AgentEvaluationSummary) -> dict[str, dict]:
    values = summary.model_dump()
    results = {}
    for name, (threshold, operator) in THRESHOLDS.items():
        value = float(values[name])
        passed = compare_metric(value, threshold, operator)
        results[name] = {
            "value": value,
            "threshold": threshold,
            "operator": operator,
            "passed": passed,
        }
    return results


def build_markdown_report(
    summary: AgentEvaluationSummary,
    threshold_report: dict[str, dict],
    case_details: list[dict],
    strict_passed: bool,
) -> str:
    lines = [
        "# STEP 12 Agent Evaluation",
        "",
        f"- Cases: {summary.case_count}",
        "- Dataset: `data/evaluation/agent_cases.json`",
        f"- Threshold gate: {'PASS' if strict_passed else 'REVIEW'}",
        "",
        "## Summary",
        "",
        f"- Task completion rate: {summary.task_completion_rate:.4f}",
        f"- Tool sequence accuracy: {summary.tool_sequence_accuracy:.4f}",
        f"- Tool F1: {summary.tool_f1:.4f}",
        f"- Tool success rate: {summary.tool_success_rate:.4f}",
        f"- Match status F1: {summary.match_status_f1:.4f}",
        f"- Citation F1: {summary.citation_f1:.4f}",
        f"- Citation validity rate: {summary.citation_validity_rate:.4f}",
        f"- Abstention accuracy: {summary.abstention_accuracy:.4f}",
        f"- Confirmation recovery rate: {summary.confirmation_recovery_rate:.4f}",
        f"- Unsupported suggestion rate: {summary.unsupported_suggestion_rate:.4f}",
        f"- Average steps: {summary.average_steps:.2f}",
        f"- Average total tokens: {summary.average_usage_total:.2f}",
        f"- p50 latency ms: {summary.p50_latency_ms:.2f}",
        f"- p95 latency ms: {summary.p95_latency_ms:.2f}",
        "",
        "## Thresholds",
        "",
        "| Metric | Value | Condition | Result |",
        "|---|---:|---|---|",
    ]

    for name, item in threshold_report.items():
        lines.append(
            "| "
            f"{name} | "
            f"{item['value']:.4f} | "
            f"{item['operator']} {item['threshold']:.4f} | "
            f"{'PASS' if item['passed'] else 'FAIL'} |"
        )

    lines.extend(
        [
            "",
            "## Failing Cases",
            "",
        ]
    )

    failing_cases = [
        case
        for case in case_details
        if not (
            case["metrics"]["task_completed"]
            and case["metrics"]["citation_valid"]
            and case["metrics"]["abstention_correct"]
            and case["metrics"]["confirmation_recovered"]
            and case["metrics"]["unsupported_suggestion_rate"] == 0
        )
    ]
    if not failing_cases:
        lines.append("- No failing cases.")
    else:
        for case in failing_cases:
            lines.append(
                "- "
                f"{case['case_id']} ({case['category']}): "
                f"task_completed={case['metrics']['task_completed']}, "
                f"citation_valid={case['metrics']['citation_valid']}, "
                f"abstention_correct={case['metrics']['abstention_correct']}, "
                f"confirmation_recovered={case['metrics']['confirmation_recovered']}, "
                f"unsupported_suggestion_rate={case['metrics']['unsupported_suggestion_rate']:.4f}"
            )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- 该评估集用于固定 Agent 行为回归，不代表真实模型质量上限。",
            "- 失败样本用于验证指标可以发现引用缺失、无依据建议和工具多调用问题。",
            "- 后续可以把真实任务执行结果转换成同结构 observation，再运行同一套指标。",
        ]
    )
    return "\n".join(lines) + "\n"


def evaluate_agent_dataset(*, limit: int = 0) -> tuple[dict, str, bool]:
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    cases = [
        AgentEvaluationCase.model_validate(item)
        for item in payload["cases"]
    ]
    if limit > 0:
        cases = cases[:limit]
    if not cases:
        raise ValueError("评估集不能为空")

    results = [evaluate_agent_case(case) for case in cases]
    summary = summarize_agent_results(
        results,
        observed_outcomes=[case.observed for case in cases],
    )
    thresholds = threshold_results(summary)
    strict_passed = all(item["passed"] for item in thresholds.values())

    case_details = [
        result.model_dump(mode="json")
        for result in results
    ]
    report = {
        "version": 1,
        "case_count": len(cases),
        "summary": summary.model_dump(mode="json"),
        "thresholds": thresholds,
        "strict_passed": strict_passed,
        "cases": case_details,
    }
    markdown = build_markdown_report(
        summary,
        thresholds,
        case_details,
        strict_passed,
    )
    return report, markdown, strict_passed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report, markdown, strict_passed = evaluate_agent_dataset(
        limit=args.limit,
    )
    REPORT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    REPORT_MARKDOWN_PATH.write_text(markdown, encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"strict_passed={strict_passed}")
    print(f"json_report={REPORT_JSON_PATH}")
    print(f"markdown_report={REPORT_MARKDOWN_PATH}")

    if args.strict and not strict_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
