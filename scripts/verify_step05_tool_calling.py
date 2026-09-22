# 手工验收岗位 JD 工具的真实模型调用链路。

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


EXPECTED_TOOL_NAME = "extract_job_requirements"

TEST_JOB_DESCRIPTION = (
    "负责 FastAPI 后端服务开发，要求熟悉 Python、Pydantic 和异步编程；"
    "有 LLM 应用开发经验者优先。"
)

REQUIRED_RESULT_KEYS = (
    "responsibilities",
    "required_skills",
    "nice_to_have",
)


# 统一输出验收失败原因并终止脚本。
def fail(message: str) -> None:
    raise SystemExit(message)


# 真实调用岗位 JD 工具并校验参数、结果和最终回答。
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
                    "请调用工具提取下面岗位 JD 的要求：\n"
                    f"{TEST_JOB_DESCRIPTION}"
                ),
            }
        ],
        registry=registry,
        context=context,
    )

    result_json = result.model_dump(mode="json")

    print("================ 工具调用验收结果 ================")
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

    if tool_arguments != {"job_description": TEST_JOB_DESCRIPTION}:
        fail("工具参数中的 job_description 与固定输入不一致")

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

    missing_keys = [
        key
        for key in REQUIRED_RESULT_KEYS
        if key not in result_data
    ]

    if missing_keys:
        fail("岗位提取结果缺少字段：" + ", ".join(missing_keys))

    if not result_data["responsibilities"]:
        fail("responsibilities 不能为空")

    if not result_data["required_skills"]:
        fail("required_skills 不能为空")

    if not isinstance(result_data["nice_to_have"], list):
        fail("nice_to_have 必须是列表")

    if not result.answer.strip():
        fail("最终回答为空")

    print("\n验收通过：" + EXPECTED_TOOL_NAME)


if __name__ == "__main__":
    asyncio.run(main())