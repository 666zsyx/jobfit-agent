# 为 Graph 节点包装安全事件和失败分类。

from __future__ import annotations

import inspect
from time import perf_counter
from collections.abc import Callable

from langgraph.errors import GraphInterrupt
from langgraph.runtime import Runtime

from app.graphs.jobfit.retry import is_retryable_graph_error
from app.graphs.jobfit.runtime import JobFitGraphContext
from app.schemas.agent_events import AgentEvent


def _safe_error_code(exc: Exception) -> str:
    """把异常转换为不暴露内部细节的安全错误码。"""

    name = type(exc).__name__
    return name if name.isascii() else "graph_node_error"


async def _emit_node_event(
    runtime: Runtime[JobFitGraphContext],
    *,
    event_type: str,
    node_name: str,
    task_id: int | None,
    data: dict | None = None,
) -> None:
    event_sink = runtime.context.get("event_sink")
    if event_sink is None:
        return

    await event_sink(
        AgentEvent(
            type=event_type,
            task_id=task_id,
            data={
                "node": node_name,
                **(data or {}),
            },
        )
    )


def wrap_graph_node(node_name: str, node: Callable):
    """为节点添加开始、完成、失败和等待确认事件。"""

    is_async = inspect.iscoroutinefunction(node)

    if is_async:

        async def wrapped(state: dict, runtime: Runtime[JobFitGraphContext]):
            started_at = perf_counter()
            await _emit_node_event(
                runtime,
                event_type="node_started",
                node_name=node_name,
                task_id=state.get("task_id"),
            )
            try:
                result = await node(state, runtime)
            except GraphInterrupt:
                await _emit_node_event(
                    runtime,
                    event_type="waiting_confirmation",
                    node_name=node_name,
                    task_id=state.get("task_id"),
                    data={"actions": ["approve", "revise", "reject"]},
                )
                raise
            except Exception as exc:
                await _emit_node_event(
                    runtime,
                    event_type="node_failed",
                    node_name=node_name,
                    task_id=state.get("task_id"),
                    data={"error_code": _safe_error_code(exc)},
                )
                if is_retryable_graph_error(exc):
                    await _emit_node_event(
                        runtime,
                        event_type="retry_scheduled",
                        node_name=node_name,
                        task_id=state.get("task_id"),
                        data={
                            "error_code": _safe_error_code(exc),
                            "max_attempts": 3,
                        },
                    )
                raise

            duration_ms = round((perf_counter() - started_at) * 1000)
            await _emit_node_event(
                runtime,
                event_type="node_finished",
                node_name=node_name,
                task_id=state.get("task_id"),
                data={"duration_ms": duration_ms},
            )
            if isinstance(result, dict):
                result = {
                    **result,
                    "node_metrics": [
                        {
                            "node": node_name,
                            "duration_ms": duration_ms,
                        }
                    ],
                }
            return result

    else:

        async def wrapped(state: dict, runtime: Runtime[JobFitGraphContext]):
            started_at = perf_counter()
            await _emit_node_event(
                runtime,
                event_type="node_started",
                node_name=node_name,
                task_id=state.get("task_id"),
            )
            try:
                result = node(state)
            except GraphInterrupt:
                await _emit_node_event(
                    runtime,
                    event_type="waiting_confirmation",
                    node_name=node_name,
                    task_id=state.get("task_id"),
                    data={"actions": ["approve", "revise", "reject"]},
                )
                raise
            except Exception as exc:
                await _emit_node_event(
                    runtime,
                    event_type="node_failed",
                    node_name=node_name,
                    task_id=state.get("task_id"),
                    data={"error_code": _safe_error_code(exc)},
                )
                raise

            duration_ms = round((perf_counter() - started_at) * 1000)
            await _emit_node_event(
                runtime,
                event_type="node_finished",
                node_name=node_name,
                task_id=state.get("task_id"),
                data={"duration_ms": duration_ms},
            )
            if isinstance(result, dict):
                result = {
                    **result,
                    "node_metrics": [
                        {
                            "node": node_name,
                            "duration_ms": duration_ms,
                        }
                    ],
                }
            return result

    wrapped.__name__ = f"{node_name}_graph_node"
    return wrapped


__all__ = ["wrap_graph_node"]
