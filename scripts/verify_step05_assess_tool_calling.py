import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.schemas.auth import CurrentUser
from app.services.tool_calling import run_tool_calling_once
from app.tools import ToolContext
from app.tools.jobfit import build_jobfit_tool_registry


EXPECTED_TOOL_NAME = "assess_requirement_match"

TEST_SEARCH_RESULT = {
    "requirements": [
        "熟悉 Python",
        "有 LLM 应用开发经验",
    ],
    "matches": [
        {
            "requirement": "熟悉 Python",
            "evidence": [
                {
                    "section_type": "skills",
                    "title": "技能",
                    "content": "Python、FastAPI、Pydantic",
                    "score": 0.5,
                }
            ],
        },
        {
            "requirement": "有 LLM 应用开发经验",
            "evidence": [],
        },
    ],
}

EXPECTED_SKILLS_CONTENT = TEST_SEARCH_RESULT["matches"][0]["evidence"][0]["content"]

FORBIDDEN_ANSWER_PHRASES = [
    "not_match",
    "明确不满足",
    "候选人不会 LLM",
]


def fail(message: str) -> None:
    raise SystemExit(message)


async def main() -> None:
    current_user = CurrentUser(
        id=1,
        username="demo_user",
        role="admin",
    )
    context = ToolContext(current_user=current_user)
    registry = build_jobfit_tool_registry()

    result = await run_tool_calling_once(
        messages=[
            {
                "role": "user",
                "content": (
                    "请调用工具 assess_requirement_match，评估下面结构化检索结果中"
                    "每条岗位要求的证据状态。必须原样使用给定的 requirements 和 "
                    "matches，不得改写证据、分数或补充不存在的结论。\n"
                    "search_result="
                    + json.dumps(TEST_SEARCH_RESULT, ensure_ascii=False)
                ),
            }
        ],
        registry=registry,
        context=context,
    )

    result_json = result.model_dump(mode="json")

    print("================ 匹配评估工具验收结果 ================")
    print(
        json.dumps(
            result_json,
            ensure_ascii=False,
            indent=2,
        )
    )

    if len(result.tool_calls) != 1:
        fail(f"预期只有一个 tool_call，实际为 {len(result.tool_calls)} 个")

    tool_call = result.tool_calls[0]

    if tool_call.name != EXPECTED_TOOL_NAME:
        fail(f"模型调用了错误的工具：{tool_call.name}")

    try:
        tool_arguments = json.loads(tool_call.arguments)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"工具参数不是合法 JSON：{exc}") from exc

    if not isinstance(tool_arguments, dict):
        fail("工具参数必须是 JSON 对象")

    if tool_arguments.get("requirements") != TEST_SEARCH_RESULT["requirements"]:
        fail("工具参数中的 requirements 与固定输入不一致")

    if tool_arguments.get("matches") != TEST_SEARCH_RESULT["matches"]:
        fail("工具参数中的 matches 与固定输入不一致")

    if len(result.tool_results) != 1:
        fail(
            "预期只有一个 tool_result，"
            f"实际为 {len(result.tool_results)} 个"
        )

    tool_result = result.tool_results[0]

    if tool_result.tool_call_id != tool_call.id:
        fail("工具结果与工具调用的 tool_call_id 不一致")

    if tool_result.name != EXPECTED_TOOL_NAME:
        fail(f"工具结果名称错误：{tool_result.name}")

    if tool_result.result.get("ok") is not True:
        fail(
            "工具执行失败："
            f"{tool_result.result.get('error', '未知错误')}"
        )

    result_data = tool_result.result.get("result")

    if not isinstance(result_data, dict):
        fail("工具结果的 result 必须是 JSON 对象")

    assessments = result_data.get("assessments")

    if not isinstance(assessments, list):
        fail("工具结果中的 assessments 必须是列表")

    if len(assessments) != 2:
        fail(f"assessment 数量错误：{len(assessments)} != 2")

    first_assessment, second_assessment = assessments

    if not isinstance(first_assessment, dict):
        fail("第一条 assessment 必须是 JSON 对象")

    if not isinstance(second_assessment, dict):
        fail("第二条 assessment 必须是 JSON 对象")

    if first_assessment.get("status") != "partial_match":
        fail(
            "第一条要求的状态应为 partial_match，"
            f"实际为 {first_assessment.get('status')}"
        )

    if second_assessment.get("status") != "insufficient_evidence":
        fail(
            "第二条要求的状态应为 insufficient_evidence，"
            f"实际为 {second_assessment.get('status')}"
        )

    first_evidence = first_assessment.get("evidence")

    if not isinstance(first_evidence, list) or not first_evidence:
        fail("第一条要求没有保留原文证据")

    evidence_contents = [
        item.get("content")
        for item in first_evidence
        if isinstance(item, dict)
    ]

    if EXPECTED_SKILLS_CONTENT not in evidence_contents:
        fail("第一条要求的证据没有保留 skills 分段原文")

    second_evidence = second_assessment.get("evidence")

    if second_evidence != []:
        fail(f"第二条要求的 evidence 应为空，实际为：{second_evidence}")

    summary = result_data.get("summary")

    if not isinstance(summary, dict):
        fail("工具结果中的 summary 必须是 JSON 对象")

    expected_summary = {
        "strong_match_count": 0,
        "partial_match_count": 1,
        "insufficient_evidence_count": 1,
    }

    if summary != expected_summary:
        fail(f"summary 与预期不一致：{summary}")

    summary_total = sum(summary.values())

    if summary_total != len(assessments):
        fail(
            "summary 总数与 assessments 数量不一致："
            f"{summary_total} != {len(assessments)}"
        )

    if not result.answer.strip():
        fail("最终回答为空")

    forbidden_found = [
        phrase
        for phrase in FORBIDDEN_ANSWER_PHRASES
        if phrase in result.answer
    ]

    if forbidden_found:
        fail(f"最终回答包含越界结论：{forbidden_found}")

    print("\n验收通过：assess_requirement_match")
    print(
        "请人工确认：最终回答保留证据不足的不确定性，"
        "没有把无证据解释成明确不满足。"
    )


if __name__ == "__main__":
    asyncio.run(main())