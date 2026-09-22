import asyncio
import json
import logging
from time import perf_counter

from pydantic import ValidationError

from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


logger = logging.getLogger(__name__)

TOOL_TIMEOUT_SECONDS = 30.0


def _argument_keys(arguments: object) -> str:
    if not isinstance(arguments, dict):
        return "[]"

    return str(sorted(str(key) for key in arguments.keys()))


def _duration_ms(started_at: float) -> int:
    return round((perf_counter() - started_at) * 1000)


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
) -> dict:
    started_at = perf_counter()
    user_id = context.current_user.id
    tool = registry.get(tool_name)

    if tool is None:
        _log_tool_call(
            logging.WARNING,
            tool_name=tool_name,
            user_id=user_id,
            status="unknown_tool",
            duration_ms=_duration_ms(started_at),
        )
        return {
            "ok": False,
            "error": "工具未注册",
        }

    argument_keys = _argument_keys(arguments)

    _log_tool_call(
        logging.INFO,
        tool_name=tool_name,
        user_id=user_id,
        status="started",
        argument_keys=argument_keys,
    )

    if not isinstance(arguments, dict):
        _log_tool_call(
            logging.WARNING,
            tool_name=tool_name,
            user_id=user_id,
            status="invalid_arguments",
            duration_ms=_duration_ms(started_at),
        )
        return {
            "ok": False,
            "error": "工具参数必须是 JSON 对象",
        }

    try:
        validated_args = tool.args_model.model_validate(arguments)
    except ValidationError:
        _log_tool_call(
            logging.WARNING,
            tool_name=tool_name,
            user_id=user_id,
            status="validation_error",
            duration_ms=_duration_ms(started_at),
            argument_keys=argument_keys,
        )
        return {
            "ok": False,
            "error": "工具参数校验失败",
        }

    try:
        result = await asyncio.wait_for(
            tool.handler(validated_args, context),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        _log_tool_call(
            logging.WARNING,
            tool_name=tool_name,
            user_id=user_id,
            status="timeout",
            duration_ms=_duration_ms(started_at),
        )
        return {
            "ok": False,
            "error": "工具执行超时",
        }
    except Exception:
        _log_tool_call(
            logging.ERROR,
            tool_name=tool_name,
            user_id=user_id,
            status="error",
            duration_ms=_duration_ms(started_at),
        )
        logger.exception("工具执行失败 tool=%s", tool_name)
        return {
            "ok": False,
            "error": "工具执行失败",
        }

    if not isinstance(result, dict):
        _log_tool_call(
            logging.ERROR,
            tool_name=tool_name,
            user_id=user_id,
            status="invalid_result",
            duration_ms=_duration_ms(started_at),
        )
        return {
            "ok": False,
            "error": "工具返回结果必须是 JSON 对象",
        }

    try:
        json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        _log_tool_call(
            logging.ERROR,
            tool_name=tool_name,
            user_id=user_id,
            status="non_serializable_result",
            duration_ms=_duration_ms(started_at),
        )
        logger.exception("工具返回值无法序列化 tool=%s", tool_name)
        return {
            "ok": False,
            "error": "工具返回结果无法序列化",
        }

    _log_tool_call(
        logging.INFO,
        tool_name=tool_name,
        user_id=user_id,
        status="success",
        duration_ms=_duration_ms(started_at),
    )

    return {
        "ok": True,
        "result": result,
    }

