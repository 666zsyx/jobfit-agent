# 提供 JobFit Graph 的业务节点，复用项目现有 LLM、工具和 RAG 能力。

from __future__ import annotations

import json
from typing import Any, Literal

from langgraph.runtime import Runtime
from langgraph.types import interrupt

from app.graphs.jobfit.runtime import JobFitGraphContext
from app.graphs.jobfit.state import (
    JobFitGraphState,
    ReactStatus,
)
from app.schemas.agent_events import AgentEvent, AgentEventSink
from app.schemas.chat import LLMWithToolsResult, TokenUsage, ToolCall
from app.schemas.knowledge import EvidencePack
from app.schemas.react_agent import ReactToolExecution
from app.services.react_agent import (
    JOBFIT_PERSISTED_SYSTEM_PROMPT,
    build_jobfit_react_messages,
)
from app.tools.executor import execute_tool, record_tool_audit_event


def _zero_usage() -> dict[str, int]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def _node_update(node_name: str) -> dict:
    """统一记录当前节点和节点轨迹。"""

    return {
        "current_node": node_name,
        "trace": [node_name],
    }


def _merge_usage(
    total: dict[str, int] | None,
    current: TokenUsage,
) -> dict[str, int]:
    """把当前模型调用 Usage 累加到 Graph State。"""

    total_usage = TokenUsage.model_validate(total or _zero_usage())
    return {
        "prompt_tokens": total_usage.prompt_tokens + current.prompt_tokens,
        "completion_tokens": (
            total_usage.completion_tokens + current.completion_tokens
        ),
        "total_tokens": total_usage.total_tokens + current.total_tokens,
    }


def _build_assistant_tool_message(
    result: LLMWithToolsResult,
) -> dict[str, Any]:
    """把模型提出的工具调用转换为 assistant 消息。"""

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


def _build_tool_message(
    tool_call_id: str,
    result: dict[str, Any],
) -> dict[str, str]:
    """把统一工具结果转换为可回传模型的 tool 消息。"""

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result, ensure_ascii=False),
    }


async def _emit_event(
    event_sink: AgentEventSink | None,
    event: AgentEvent,
) -> None:
    if event_sink is not None:
        await event_sink(event)


def _restore_evidence_packs(
    state: JobFitGraphState,
) -> list[EvidencePack]:
    """从 Graph State 恢复 EvidencePack 对象。"""

    restored: list[EvidencePack] = []
    for item in state.get("retrieved_evidence_packs", []):
        if isinstance(item, EvidencePack):
            restored.append(item)
        else:
            restored.append(EvidencePack.model_validate(item))
    return restored


def prepare_run(state: JobFitGraphState) -> dict:
    """校验运行参数并初始化工作流。"""

    task_id = state.get("task_id")
    job_id = state.get("job_id")
    resume_version_id = state.get("resume_version_id")
    max_steps = state.get("max_steps", 8)

    if task_id is None or task_id <= 0:
        raise ValueError("task_id 必须大于 0")
    if job_id is None or job_id <= 0:
        raise ValueError("job_id 必须大于 0")
    if resume_version_id is None or resume_version_id <= 0:
        raise ValueError("resume_version_id 必须大于 0")
    if max_steps <= 0:
        raise ValueError("max_steps 必须大于 0")

    return {
        **_node_update("prepare_run"),
        "status": "running",
        "current_step": 0,
        "max_steps": max_steps,
        "usage": _zero_usage(),
        "tool_calls": [],
        "pending_report": None,
        "final_answer": None,
        "react_status": None,
        "error_code": None,
    }


def load_context(state: JobFitGraphState) -> dict:
    """构造 ReAct 初始消息。"""

    if state.get("messages"):
        return {
            **_node_update("load_context"),
            "context_loaded": True,
        }

    messages = build_jobfit_react_messages(
        job_description=state.get("job_description", ""),
        resume_text=state.get("resume_text", ""),
        system_prompt=state.get(
            "system_prompt",
            JOBFIT_PERSISTED_SYSTEM_PROMPT,
        ),
        conversation_context=state.get("conversation_context"),
    )

    return {
        **_node_update("load_context"),
        "messages": messages,
        "context_loaded": True,
    }


async def agent_decide(
    state: JobFitGraphState,
    runtime: Runtime[JobFitGraphContext],
) -> dict:
    """节点：调用 LLM 决定下一步工具调用或最终回答。"""

    current_step = state.get("current_step", 0) + 1
    registry = runtime.context["tool_registry"]
    event_sink = runtime.context.get("event_sink")

    await _emit_event(
        event_sink,
        AgentEvent(
            type="step_started",
            task_id=state.get("task_id"),
            step=current_step,
        ),
    )

    model_result = await runtime.context["chat_with_tools"](
        messages=state.get("messages", []),
        tools=registry.openai_definitions(),
    )

    update = {
        **_node_update("agent_decide"),
        "current_step": current_step,
        "usage": _merge_usage(state.get("usage"), model_result.usage),
    }

    if model_result.tool_calls:
        update["tool_calls"] = [
            tool_call.model_dump(mode="json")
            for tool_call in model_result.tool_calls
        ]
        update["messages"] = [
            _build_assistant_tool_message(model_result)
        ]
        update["final_answer"] = None
        return update

    update["tool_calls"] = []
    update["final_answer"] = model_result.content or ""
    update["react_status"] = "completed"

    await _emit_event(
        event_sink,
        AgentEvent(
            type="content",
            task_id=state.get("task_id"),
            step=current_step,
            content=model_result.content or "",
        ),
    )
    return update


async def execute_tools(
    state: JobFitGraphState,
    runtime: Runtime[JobFitGraphContext],
) -> dict:
    """节点：解析并执行模型提出的工具调用。"""

    tool_calls = [
        ToolCall.model_validate(item)
        for item in state.get("tool_calls", [])
    ]
    if not tool_calls:
        return _node_update("execute_tools")

    step = state.get("current_step", 1)
    context = runtime.context["tool_context_factory"](state, step)
    context.step_no = step
    context.pending_report = state.get("pending_report")
    context.retrieved_evidence_packs = _restore_evidence_packs(state)

    registry = runtime.context["tool_registry"]
    event_sink = runtime.context.get("event_sink")
    trace: list[ReactToolExecution] = []
    tool_messages: list[dict[str, str]] = []

    for tool_call in tool_calls:
        await _emit_event(
            event_sink,
            AgentEvent(
                type="tool_started",
                task_id=state.get("task_id"),
                step=step,
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
            ),
        )

        parsed_arguments: dict[str, Any] | None = None

        try:
            raw_arguments = json.loads(tool_call.arguments)
        except json.JSONDecodeError:
            execution_result = {
                "ok": False,
                "error": "工具参数解析失败",
            }
            record_tool_audit_event(
                context=context,
                step_no=step,
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                status="validation_error",
                duration_ms=0,
                error_code="invalid_tool_arguments",
            )
        else:
            if isinstance(raw_arguments, dict):
                parsed_arguments = raw_arguments

            execution_result = await execute_tool(
                registry=registry,
                tool_name=tool_call.name,
                arguments=raw_arguments,
                context=context,
                step_no=step,
                tool_call_id=tool_call.id,
            )

        await _emit_event(
            event_sink,
            AgentEvent(
                type="tool_finished",
                task_id=state.get("task_id"),
                step=step,
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                data={
                    "ok": bool(execution_result.get("ok")),
                    "error": execution_result.get("error"),
                },
            ),
        )

        trace.append(
            ReactToolExecution(
                step=step,
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                arguments=parsed_arguments,
                result=execution_result,
            )
        )
        tool_messages.append(
            _build_tool_message(
                tool_call_id=tool_call.id,
                result=execution_result,
            )
        )

    return {
        **_node_update("execute_tools"),
        "messages": tool_messages,
        "tool_calls": [],
        "tool_trace": [
            item.model_dump(mode="json")
            for item in trace
        ],
        "tool_audit_events": [
            event.model_dump(mode="json")
            for event in context.tool_audit_events
        ],
        "retrieved_evidence_packs": [
            pack.model_dump(mode="json")
            for pack in context.retrieved_evidence_packs
        ],
        "pending_report": context.pending_report,
    }


def assess_evidence(state: JobFitGraphState) -> dict:
    """节点：整理待确认报告，并在没有报告时生成安全回退结果。"""

    pending_report = state.get("pending_report")
    react_status: ReactStatus = (
        state.get("react_status") or "max_steps_reached"
    )

    if pending_report is None:
        pending_report = {
            "summary": (
                state.get("final_answer")
                or "ReAct 达到最大步数，未生成最终回答。"
            ),
            "result_json": {
                "react_status": react_status,
                "answer": state.get("final_answer"),
                "steps": state.get("current_step", 0),
                "trace": state.get("tool_trace", []),
                "usage": state.get("usage", _zero_usage()),
            },
        }

    return {
        **_node_update("assess_evidence"),
        "pending_report": pending_report,
        "react_status": react_status,
    }


def human_confirmation(state: JobFitGraphState) -> dict:
    """节点：暂停工作流并等待人工确认。"""

    payload = interrupt(
        {
            "type": "human_confirmation",
            "pending_report": state.get("pending_report"),
            "actions": ["approve", "revise", "reject"],
        }
    )

    if not isinstance(payload, dict):
        raise TypeError("人工确认 resume 数据必须是字典")

    decision = payload.get("decision")
    if decision not in {"approve", "revise", "reject"}:
        raise ValueError("decision 只能是 approve、revise 或 reject")

    reviewed_report = None
    resume_revision_text = None

    if decision == "reject":
        reviewed_report = None
    elif decision == "revise":
        edited_report = payload.get("edited_report")
        if edited_report is not None and not isinstance(edited_report, dict):
            raise ValueError("edited_report 必须是 JSON 对象")
        reviewed_report = (
            edited_report
            if isinstance(edited_report, dict)
            else state.get("pending_report")
        )

        raw_revision_text = payload.get("resume_revision_text")
        if raw_revision_text is not None:
            resume_revision_text = str(raw_revision_text).strip()
            if not resume_revision_text:
                raise ValueError("resume_revision_text 不能为空")
    else:
        reviewed_report = state.get("pending_report")

    return {
        **_node_update("human_confirmation"),
        "confirmation_decision": decision,
        "reviewed_report": reviewed_report,
        "resume_revision_text": resume_revision_text,
    }


def save_report(state: JobFitGraphState) -> dict:
    """阶段三仍然使用假报告 ID，数据库写入留待后续阶段。"""

    return {
        **_node_update("save_report"),
        "report_id": 101,
        "status": "report_saved",
    }


def finalize(state: JobFitGraphState) -> dict:
    """标记工作流成功结束。"""

    return {
        **_node_update("finalize"),
        "status": "completed",
    }


def cancel(state: JobFitGraphState) -> dict:
    """用户拒绝时取消工作流。"""

    return {
        **_node_update("cancel"),
        "status": "cancelled",
        "error_code": "user_rejected",
    }


def route_after_agent(
    state: JobFitGraphState,
) -> Literal["execute_tools", "assess_evidence"]:
    """模型提出工具调用时执行工具，否则进入证据整理。"""

    if state.get("tool_calls"):
        return "execute_tools"
    return "assess_evidence"


def route_after_tools(
    state: JobFitGraphState,
) -> Literal["agent_decide", "assess_evidence"]:
    """达到最大决策轮数后停止循环。"""

    if state.get("current_step", 0) < state.get("max_steps", 8):
        return "agent_decide"
    return "assess_evidence"


def route_after_confirmation(
    state: JobFitGraphState,
) -> Literal["save_report", "cancel"]:
    """拒绝时取消，其余情况保存报告。"""

    if state.get("confirmation_decision") == "reject":
        return "cancel"
    return "save_report"


__all__ = [
    "agent_decide",
    "assess_evidence",
    "cancel",
    "execute_tools",
    "finalize",
    "human_confirmation",
    "load_context",
    "prepare_run",
    "route_after_agent",
    "route_after_confirmation",
    "route_after_tools",
    "save_report",
]
