import asyncio
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.schemas.auth import CurrentUser
from app.services.tool_calling import run_tool_calling_once
from app.tools import ToolContext
from app.tools.jobfit import build_jobfit_tool_registry


EXPECTED_TOOL_NAME = "search_resume_evidence"

TEST_REQUIREMENTS = [
    "熟悉 Python",
    "有 LLM 应用开发经验",
]

TEST_SECTIONS = [
    {
        "section_type": "skills",
        "title": "技能",
        "content": "Python、FastAPI、Pydantic",
    },
    {
        "section_type": "project_experience",
        "title": "项目经历",
        "content": "使用 FastAPI 开发岗位匹配服务，负责接口设计和数据处理",
    },
]

EXPECTED_SKILLS_CONTENT = TEST_SECTIONS[0]["content"]


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
                    "请调用工具 search_resume_evidence 检索下面岗位要求"
                    "在简历分段中的原文证据。必须原样使用给定的 "
                    "requirements 和 sections，不要改写或补充。\n"
                    f"requirements={json.dumps(TEST_REQUIREMENTS, ensure_ascii=False)}\n"
                    f"sections={json.dumps(TEST_SECTIONS, ensure_ascii=False)}"
                ),
            }
        ],
        registry=registry,
        context=context,
    )

    result_json = result.model_dump(mode="json")

    print("================ 证据工具调用验收结果 ================")
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

    if tool_arguments.get("requirements") != TEST_REQUIREMENTS:
        fail("工具参数中的 requirements 与固定输入不一致")

    if tool_arguments.get("sections") != TEST_SECTIONS:
        fail("工具参数中的 sections 与固定输入不一致")

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

    if result_data.get("requirements") != TEST_REQUIREMENTS:
        fail("工具结果中的 requirements 与固定输入不一致")

    matches = result_data.get("matches")

    if not isinstance(matches, list):
        fail("工具结果中的 matches 必须是列表")

    if len(matches) != len(TEST_REQUIREMENTS):
        fail(
            "matches 数量与 requirements 不一致："
            f"{len(matches)} != {len(TEST_REQUIREMENTS)}"
        )

    actual_requirements = []

    for index, match in enumerate(matches):
        if not isinstance(match, dict):
            fail(f"第 {index + 1} 个 match 必须是 JSON 对象")

        actual_requirements.append(match.get("requirement"))

    if actual_requirements != TEST_REQUIREMENTS:
        fail(
            "matches 中 requirement 的顺序与输入不一致："
            f"{actual_requirements}"
        )

    first_evidence = matches[0].get("evidence")

    if not isinstance(first_evidence, list) or not first_evidence:
        fail("“熟悉 Python”没有返回任何证据")

    evidence_contents = [
        item.get("content")
        for item in first_evidence
        if isinstance(item, dict)
    ]

    if EXPECTED_SKILLS_CONTENT not in evidence_contents:
        fail("第一条要求的证据中没有保留 skills 分段原文")

    second_evidence = matches[1].get("evidence")

    if second_evidence != []:
        fail(
            "“有 LLM 应用开发经验”不应返回证据，"
            f"实际为：{second_evidence}"
        )

    if not result.answer.strip():
        fail("最终回答为空")

    print("\n验收通过：search_resume_evidence")
    print(
        "请人工确认：最终回答没有声称找到了 LLM 应用开发经验。"
    )


if __name__ == "__main__":
    asyncio.run(main())
