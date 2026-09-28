# 手工验收 STEP 06 的完整 JobFit ReAct Agent 真实模型链路。

import asyncio
import json
import sys
from typing import Any
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.schemas.auth import CurrentUser
from app.schemas.react_agent import ReactAgentResult, ReactToolExecution
from app.services.react_agent import run_jobfit_agent
from app.tools import ToolContext


MAX_STEPS = 8

TEST_JOB_DESCRIPTION = (
    "岗位：Python 后端实习生。"
    "职责：使用 FastAPI 开发后端接口，参与 Agent 应用开发。"
    "要求：熟悉 Python；了解 Pydantic 和异步编程；"
    "有 LLM 应用开发经验者优先。"
)

TEST_RESUME_TEXT = (
    "姓名：张三。"
    "技能：Python、FastAPI、Pydantic、异步编程基础。"
    "项目：使用 FastAPI 完成课程项目，并调用大模型 API 实现多轮问答。"
)

REQUIRED_TOOLS = (
    "extract_job_requirements",
    "extract_resume_sections",
    "search_resume_evidence",
    "assess_requirement_match",
)

EXTRACTION_TOOLS = (
    "extract_job_requirements",
    "extract_resume_sections",
)

MATCH_STATUSES = {
    "strong_match",
    "partial_match",
    "insufficient_evidence",
}


# 统一输出验收失败原因并终止脚本。
def fail(message: str) -> None:
    raise SystemExit(f"验收失败：{message}")


# 构造不包含完整参数和完整工具结果的 trace 安全摘要。
def build_trace_summary(
    trace: list[ReactToolExecution],
) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []

    for item in trace:
        result_payload = item.result.get("result")
        result_keys = (
            sorted(result_payload.keys())
            if isinstance(result_payload, dict)
            else []
        )
        summary_item = {
            "step": item.step,
            "tool_name": item.tool_name,
            "ok": item.result.get("ok"),
            "result_keys": result_keys,
        }

        if item.result.get("ok") is False:
            summary_item["error"] = item.result.get("error")

        summary.append(summary_item)

    return summary


# 校验 Token Usage 字段完整且总量一致。
def validate_usage(result: ReactAgentResult) -> None:
    usage = result.usage

    if usage.prompt_tokens < 0 or usage.completion_tokens < 0:
        fail("Token Usage 不能为负数")

    if usage.total_tokens <= 0:
        fail("Token Usage 必须大于 0")

    expected_total = usage.prompt_tokens + usage.completion_tokens

    if usage.total_tokens != expected_total:
        fail(
            "Token Usage 总量不一致："
            f"{usage.total_tokens} != {expected_total}"
        )


# 校验某个工具成功结果中的业务 payload 是字典。
def get_success_payload(item: ReactToolExecution) -> dict[str, Any]:
    if item.result.get("ok") is not True:
        fail(
            f"第 {item.step} 步工具 {item.tool_name} 执行失败："
            f"{item.result.get('error', '未知错误')}"
        )

    payload = item.result.get("result")

    if not isinstance(payload, dict):
        fail(f"工具 {item.tool_name} 的 result 必须是 JSON 对象")

    return payload


# 校验非空列表字段。
def validate_non_empty_list(
    payload: dict[str, Any],
    field_name: str,
    tool_name: str,
) -> list[Any]:
    value = payload.get(field_name)

    if not isinstance(value, list) or not value:
        fail(f"工具 {tool_name} 的 {field_name} 必须是非空列表")

    return value


# 校验四个工具各自的关键输出结构。
def validate_tool_payload(item: ReactToolExecution) -> None:
    payload = get_success_payload(item)

    if item.tool_name == "extract_job_requirements":
        validate_non_empty_list(payload, "responsibilities", item.tool_name)
        validate_non_empty_list(payload, "required_skills", item.tool_name)

        if not isinstance(payload.get("nice_to_have"), list):
            fail("extract_job_requirements 的 nice_to_have 必须是列表")

    elif item.tool_name == "extract_resume_sections":
        sections = validate_non_empty_list(
            payload,
            "sections",
            item.tool_name,
        )

        for index, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                fail(f"第 {index} 个简历分段不是 JSON 对象")

            for key in ("section_type", "title", "content"):
                value = section.get(key)

                if not isinstance(value, str) or not value.strip():
                    fail(f"第 {index} 个简历分段缺少有效字段 {key}")

    elif item.tool_name == "search_resume_evidence":
        requirements = validate_non_empty_list(
            payload,
            "requirements",
            item.tool_name,
        )
        matches = validate_non_empty_list(
            payload,
            "matches",
            item.tool_name,
        )

        if len(requirements) != len(matches):
            fail("search_resume_evidence 的 requirements 和 matches 数量不一致")

        for match in matches:
            if not isinstance(match, dict):
                fail("search_resume_evidence 的 match 必须是 JSON 对象")

            if not isinstance(match.get("requirement"), str):
                fail("search_resume_evidence 的 match 缺少 requirement")

            if not isinstance(match.get("evidence"), list):
                fail("search_resume_evidence 的 match 缺少 evidence 列表")

    elif item.tool_name == "assess_requirement_match":
        assessments = validate_non_empty_list(
            payload,
            "assessments",
            item.tool_name,
        )
        summary = payload.get("summary")

        if not isinstance(summary, dict):
            fail("assess_requirement_match 的 summary 必须是 JSON 对象")

        actual_counts = {
            "strong_match": 0,
            "partial_match": 0,
            "insufficient_evidence": 0,
        }

        for assessment in assessments:
            if not isinstance(assessment, dict):
                fail("assess_requirement_match 的 assessment 必须是 JSON 对象")

            status = assessment.get("status")

            if status not in MATCH_STATUSES:
                fail(f"出现未知匹配状态：{status}")

            actual_counts[status] += 1

        expected_counts = {
            "strong_match": summary.get("strong_match_count"),
            "partial_match": summary.get("partial_match_count"),
            "insufficient_evidence": summary.get(
                "insufficient_evidence_count"
            ),
        }

        if actual_counts != expected_counts:
            fail("assess_requirement_match 的 summary 与 assessments 数量不一致")

    else:
        fail(f"出现未预期工具：{item.tool_name}")


# 校验工具调用顺序符合四个 JobFit 工具的依赖关系。
def validate_tool_sequence(trace: list[ReactToolExecution]) -> None:
    tool_names = [item.tool_name for item in trace]

    for tool_name in REQUIRED_TOOLS:
        if tool_name not in tool_names:
            fail(f"缺少必要工具调用：{tool_name}")

    extraction_indexes = [
        tool_names.index(tool_name)
        for tool_name in EXTRACTION_TOOLS
    ]
    search_index = tool_names.index("search_resume_evidence")
    assess_index = tool_names.index("assess_requirement_match")

    if search_index <= max(extraction_indexes):
        fail("search_resume_evidence 必须在两项提取之后调用")

    if assess_index <= search_index:
        fail("assess_requirement_match 必须在证据检索之后调用")


# 校验完整 ReAct 结果并输出不含完整正文的验收摘要。
def validate_result(result: ReactAgentResult) -> None:
    if result.status != "completed":
        fail(f"ReAct 未正常完成，status={result.status}")

    if not isinstance(result.answer, str) or not result.answer.strip():
        fail("最终回答不能为空")

    if not any(status in result.answer for status in MATCH_STATUSES):
        fail("最终回答没有说明 strong_match、partial_match 或 insufficient_evidence")

    if result.max_steps != MAX_STEPS:
        fail(f"max_steps 错误：{result.max_steps} != {MAX_STEPS}")

    if result.steps < 1 or result.steps > MAX_STEPS:
        fail(f"steps 超出范围：{result.steps}")

    if result.latency_ms < 0:
        fail("latency_ms 不能为负数")

    if not result.trace:
        fail("工具执行轨迹不能为空")

    for item in result.trace:
        if item.step < 1 or item.step > result.steps:
            fail(f"trace step 超出范围：{item.step}")

        if item.arguments is None:
            fail(f"工具 {item.tool_name} 的参数字典为空")

        validate_tool_payload(item)

    validate_tool_sequence(result.trace)
    validate_usage(result)


# 真实运行 ReAct Agent，并打印安全、可核验的验收结果。
async def main() -> None:
    current_user = CurrentUser(
        id=1,
        username="demo_user",
        role="admin",
    )
    context = ToolContext(current_user=current_user)

    result = await run_jobfit_agent(
        job_description=TEST_JOB_DESCRIPTION,
        resume_text=TEST_RESUME_TEXT,
        context=context,
        max_steps=MAX_STEPS,
    )

    print("================ STEP 06 ReAct Agent 验收结果 ================")
    print(f"status: {result.status}")
    print(f"steps: {result.steps}")
    print(f"max_steps: {result.max_steps}")
    print(
        "usage: "
        + json.dumps(
            result.usage.model_dump(mode="json"),
            ensure_ascii=False,
        )
    )
    print(f"latency_ms: {result.latency_ms}")
    print("answer:")
    print(result.answer)
    print("trace:")
    print(
        json.dumps(
            build_trace_summary(result.trace),
            ensure_ascii=False,
            indent=2,
        )
    )

    validate_result(result)
    print("\n验收通过：STEP 06 ReAct Agent")


if __name__ == "__main__":
    asyncio.run(main())
