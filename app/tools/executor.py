# 统一校验、限时、执行和记录工具调用。

import asyncio
import json
import logging
from time import perf_counter

from pydantic import ValidationError

from app.schemas.tool_audit import ToolAuditEvent, ToolAuditStatus
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


logger = logging.getLogger(__name__)

TOOL_TIMEOUT_SECONDS = 30.0


def _argument_key_list(arguments: object) -> list[str]:
    if not isinstance(arguments, dict):
        return []

    return sorted(str(key) for key in arguments.keys())


def _argument_keys(arguments: object) -> str:
    return str(_argument_key_list(arguments))


def _duration_ms(started_at: float) -> int:
    return round((perf_counter() - started_at) * 1000)


def _start_tool_audit(
    *,
    context: ToolContext,
    step_no: int | None,
    tool_call_id: str | None,
    tool_name: str,
    argument_keys: list[str],
) -> ToolAuditEvent | None:
    if not context.collect_tool_audit:
        return None

    if step_no is None or not tool_call_id:
        return None

    event = ToolAuditEvent(
        step_no=step_no,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        status="started",
        duration_ms=None,
        error_code=None,
        argument_keys=list(argument_keys),
    )
    context.tool_audit_events.append(event)
    return event


def _finish_tool_audit(
    event: ToolAuditEvent | None,
    *,
    status: ToolAuditStatus,
    duration_ms: int,
    error_code: str | None = None,
) -> None:
    if event is None:
        return

    event.status = status
    event.duration_ms = max(duration_ms, 0)
    event.error_code = error_code


def record_tool_audit_event(
    *,
    context: ToolContext,
    step_no: int | None,
    tool_call_id: str | None,
    tool_name: str,
    status: ToolAuditStatus,
    duration_ms: int | None = None,
    error_code: str | None = None,
    argument_keys: list[str] | None = None,
) -> ToolAuditEvent | None:
    """记录 ReAct 循环外部产生的工具审计终态。"""

    if not context.collect_tool_audit:
        return None

    if step_no is None or not tool_call_id:
        return None

    event = ToolAuditEvent(
        step_no=step_no,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        status=status,
        duration_ms=duration_ms,
        error_code=error_code,
        argument_keys=list(argument_keys or []),
    )
    context.tool_audit_events.append(event)
    return event


def _log_tool_call(
    level: int,
    *,
    tool_name: str,
    user_id: int,
    status: str,
    duration_ms: int | None = None,
    argument_keys: str | None = None,
) -> None:
    fields = [
        "tool_call",
        f"tool={tool_name}",
        f"user_id={user_id}",
        f"status={status}",
    ]

    if argument_keys is not None:
        fields.append(f"argument_keys={argument_keys}")

    if duration_ms is not None:
        fields.append(f"duration_ms={duration_ms}")

    logger.log(level, " ".join(fields))

async def execute_tool(
    registry: ToolRegistry,
    tool_name: str,
    arguments: object,
    context: ToolContext,
    step_no: int | None = None,
    tool_call_id: str | None = None,
) -> dict:
    started_at = perf_counter()
    user_id = context.current_user.id
    key_list = _argument_key_list(arguments)
    audit_event = _start_tool_audit(
        context=context,
        step_no=step_no,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        argument_keys=key_list,
    )
    tool = registry.get(tool_name)

    if tool is None:
        duration_ms = _duration_ms(started_at)
        _finish_tool_audit(
            audit_event,
            status="unknown_tool",
            duration_ms=duration_ms,
            error_code="unknown_tool",
        )
        _log_tool_call(
            logging.WARNING,
            tool_name=tool_name,
            user_id=user_id,
            status="unknown_tool",
            duration_ms=duration_ms,
        )
        return {"ok": False, "error": "工具未注册"}

    argument_keys = str(key_list)
    _log_tool_call(
        logging.INFO,
        tool_name=tool_name,
        user_id=user_id,
        status="started",
        argument_keys=argument_keys,
    )

    if not isinstance(arguments, dict):
        duration_ms = _duration_ms(started_at)
        _finish_tool_audit(
            audit_event,
            status="validation_error",
            duration_ms=duration_ms,
            error_code="invalid_arguments",
        )
        _log_tool_call(
            logging.WARNING,
            tool_name=tool_name,
            user_id=user_id,
            status="invalid_arguments",
            duration_ms=duration_ms,
        )
        return {"ok": False, "error": "工具参数必须是 JSON 对象"}

    try:
        validated_args = tool.args_model.model_validate(arguments)
    except ValidationError:
        duration_ms = _duration_ms(started_at)
        _finish_tool_audit(
            audit_event,
            status="validation_error",
            duration_ms=duration_ms,
            error_code="validation_error",
        )
        _log_tool_call(
            logging.WARNING,
            tool_name=tool_name,
            user_id=user_id,
            status="validation_error",
            duration_ms=duration_ms,
            argument_keys=argument_keys,
        )
        return {"ok": False, "error": "工具参数校验失败"}

    try:
        result = await asyncio.wait_for(
            tool.handler(validated_args, context),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        duration_ms = _duration_ms(started_at)
        _finish_tool_audit(
            audit_event,
            status="timeout",
            duration_ms=duration_ms,
            error_code="timeout",
        )
        _log_tool_call(
            logging.WARNING,
            tool_name=tool_name,
            user_id=user_id,
            status="timeout",
            duration_ms=duration_ms,
        )
        return {"ok": False, "error": "工具执行超时"}
    except Exception:
        duration_ms = _duration_ms(started_at)
        _finish_tool_audit(
            audit_event,
            status="error",
            duration_ms=duration_ms,
            error_code="handler_error",
        )
        _log_tool_call(
            logging.ERROR,
            tool_name=tool_name,
            user_id=user_id,
            status="error",
            duration_ms=duration_ms,
        )
        logger.exception("工具执行失败 tool=%s", tool_name)
        return {"ok": False, "error": "工具执行失败"}

    if not isinstance(result, dict):
        duration_ms = _duration_ms(started_at)
        _finish_tool_audit(
            audit_event,
            status="error",
            duration_ms=duration_ms,
            error_code="invalid_result",
        )
        _log_tool_call(
            logging.ERROR,
            tool_name=tool_name,
            user_id=user_id,
            status="invalid_result",
            duration_ms=duration_ms,
        )
        return {"ok": False, "error": "工具返回结果必须是 JSON 对象"}

    try:
        json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        duration_ms = _duration_ms(started_at)
        _finish_tool_audit(
            audit_event,
            status="error",
            duration_ms=duration_ms,
            error_code="non_serializable_result",
        )
        _log_tool_call(
            logging.ERROR,
            tool_name=tool_name,
            user_id=user_id,
            status="non_serializable_result",
            duration_ms=duration_ms,
        )
        logger.exception("工具返回值无法序列化 tool=%s", tool_name)
        return {"ok": False, "error": "工具返回结果无法序列化"}

    duration_ms = _duration_ms(started_at)
    _finish_tool_audit(
        audit_event,
        status="success",
        duration_ms=duration_ms,
    )
    _log_tool_call(
        logging.INFO,
        tool_name=tool_name,
        user_id=user_id,
        status="success",
        duration_ms=duration_ms,
    )
    return {"ok": True, "result": result}