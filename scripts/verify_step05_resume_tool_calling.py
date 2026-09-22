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


EXPECTED_TOOL_NAME = "extract_resume_sections"

TEST_RESUME_TEXT = (
    "教育经历\n"
    "某大学 计算机科学专业\n\n"
    "项目经历\n"
    "使用 FastAPI 开发岗位匹配服务，负责接口设计和数据处理\n\n"
    "技能\n"
    "Python、FastAPI、Pydantic"
)

REQUIRED_SECTION_KEYS = (
    "section_type",
    "title",
    "content",
)


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
                    "请调用工具提取下面简历原文中的结构化分段：\n"
                    f"{TEST_RESUME_TEXT}"
                ),
            }
        ],
        registry=registry,
        context=context,
    )

    result_json = result.model_dump(mode="json")

    print("================ 简历工具调用验收结果 ================")
    print(json.dumps(result_json, ensure_ascii=False, indent=2))

    if len(result.tool_calls) != 1:
        fail(f"预期只有一个 tool_call，实际为 {len(result.tool_calls)} 个")

    tool_call = result.tool_calls[0]

    if tool_call.name != EXPECTED_TOOL_NAME:
        fail(f"模型调用了错误的工具：{tool_call.name}")

    try:
        tool_arguments = json.loads(tool_call.arguments)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"工具参数不是合法 JSON：{exc}") from exc

    if tool_arguments != {"resume_text": TEST_RESUME_TEXT}:
        fail("工具参数中的 resume_text 与固定测试简历不一致")

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

    sections = result_data.get("sections")

    if not isinstance(sections, list) or not sections:
        fail("工具结果中的 sections 不能为空")

    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            fail(f"第 {index} 个 section 必须是 JSON 对象")

        missing_keys = [
            key
            for key in REQUIRED_SECTION_KEYS
            if key not in section
        ]

        if missing_keys:
            fail(
                f"第 {index} 个 section 缺少字段："
                + ", ".join(missing_keys)
            )

        for key in REQUIRED_SECTION_KEYS:
            value = section[key]

            if not isinstance(value, str) or not value.strip():
                fail(
                    f"第 {index} 个 section 的 {key} 不能为空"
                )

    if not result.answer.strip():
        fail("最终回答为空")

    print("\n验收通过：" + EXPECTED_TOOL_NAME)


if __name__ == "__main__":
    asyncio.run(main())