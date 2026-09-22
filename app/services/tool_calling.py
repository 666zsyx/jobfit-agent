import json
from time import perf_counter
from typing import Any

from app.schemas.chat import LLMWithToolsResult, TokenUsage
from app.schemas.tool_calling import (
    ToolCallingResult,
    ToolExecutionRecord,
)
from app.services.llm import chat, chat_with_tools
from app.tools import ToolContext, ToolRegistry, execute_tool


# 把模型返回的工具调用转换成 assistant 消息
def _build_assistant_tool_message(
    result: LLMWithToolsResult,
) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": result.content,
        "tool_calls": [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            }
            for tool_call in result.tool_calls
        ],
    }


# 把工具执行结果转换成 tool 消息
def _build_tool_message(
    tool_call_id: str,
    result: dict[str, Any],
) -> dict[str, str]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        # 工具结果必须以 JSON 字符串放回消息历史
        "content": json.dumps(result, ensure_ascii=False),
    }


# 汇总第一次和第二次模型调用的 Token Usage
def _merge_usage(
    first: TokenUsage,
    second: TokenUsage,
) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=first.prompt_tokens + second.prompt_tokens,
        completion_tokens=(
            first.completion_tokens + second.completion_tokens
        ),
        total_tokens=first.total_tokens + second.total_tokens,
    )


# 只执行一次 Function Calling 往返，不实现 ReAct 循环
async def run_tool_calling_once(
    messages: list[dict[str, Any]],
    registry: ToolRegistry,
    context: ToolContext,
) -> ToolCallingResult:
    started_at = perf_counter()

    # 第一次调用模型，并把可用工具定义交给模型
    first_result = await chat_with_tools(
        messages=messages,
        tools=registry.openai_definitions(),
    )

    # 模型直接回答时，不需要执行工具或第二次调用模型
    if not first_result.tool_calls:
        latency_ms = round((perf_counter() - started_at) * 1000)

        return ToolCallingResult(
            answer=first_result.content or "",
            tool_calls=[],
            tool_results=[],
            usage=first_result.usage,
            latency_ms=latency_ms,
        )

    # 保留原始消息，并追加模型的 assistant tool_calls 消息
    updated_messages = [
        *messages,
        _build_assistant_tool_message(first_result),
    ]
    execution_records: list[ToolExecutionRecord] = []

    # 按顺序执行模型提议的每个工具
    for tool_call in first_result.tool_calls:
        try:
            # 模型返回的 arguments 是 JSON 字符串，需要由工具层解析
            arguments = json.loads(tool_call.arguments)
        except json.JSONDecodeError:
            # JSON 解析失败时返回安全错误，不中断整个流程
            execution_result = {
                "ok": False,
                "error": "工具参数解析失败",
            }
        else:
            # 解析成功后，交给工具执行器进行 Pydantic 校验和调用
            execution_result = await execute_tool(
                registry=registry,
                tool_name=tool_call.name,
                arguments=arguments,
                context=context,
            )

        # 保存当前工具的执行记录
        execution_records.append(
            ToolExecutionRecord(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                result=execution_result,
            )
        )

        # 把当前工具结果追加到消息历史，供第二次模型调用使用
        updated_messages.append(
            _build_tool_message(
                tool_call_id=tool_call.id,
                result=execution_result,
            )
        )

    # 第二次调用不再传入 tools，只负责根据工具结果生成最终回答
    final_result = await chat(messages=updated_messages)
    latency_ms = round((perf_counter() - started_at) * 1000)

    return ToolCallingResult(
        answer=final_result.answer,
        tool_calls=first_result.tool_calls,
        tool_results=execution_records,
        usage=_merge_usage(
            first_result.usage,
            final_result.usage,
        ),
        latency_ms=latency_ms,
    )