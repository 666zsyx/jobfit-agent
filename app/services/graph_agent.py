# 使用 LangGraph 和 PostgreSQL Checkpoint 执行持久化岗位分析任务。

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from uuid import uuid4

from langgraph.types import Command
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cache.task_state import (
    acquire_task_run_lock,
    release_task_run_lock,
)
from app.core.cost_tracking import (
    UsageRecord,
    summarize_usage_cost,
)
from app.core.exceptions import LLMServiceError, TaskStateConflictError
from app.core.observability import (
    build_task_metrics,
    get_request_id,
    reset_task_id,
    set_task_id,
)
from app.db.checkpoint import (
    build_checkpoint_config,
    open_postgres_checkpointer,
)
from app.graphs.jobfit import JobFitGraphContext, build_jobfit_graph
from app.repositories import (
    AnalysisTaskRepository,
    ReportRepository,
    ResumeVersionRepository,
)
from app.schemas.agent_events import AgentEvent, AgentEventSink
from app.schemas.analysis_task_api import GraphTaskExecutionResult
from app.schemas.auth import CurrentUser
from app.schemas.tool_audit import ToolAuditEvent
from app.services.analysis_results import (
    complete_analysis_task,
    mark_analysis_task_waiting_confirmation,
    persist_tool_audit_events,
)
from app.services.persisted_agent import (
    _cache_run_status_safely,
    _emit_event,
    _persist_failure_state,
    _prepare_rag_safely,
    _prepare_run_snapshot,
)
from app.services.react_agent import (
    JOBFIT_PERSISTED_SYSTEM_PROMPT,
    chat_with_tools,
)
from app.tools.base import ToolContext
from app.tools.jobfit import build_jobfit_tool_registry


logger = logging.getLogger(__name__)
RUNNABLE_GRAPH_START_STATUSES = {"pending", "interrupted"}
RESUMABLE_GRAPH_STATUSES = {"waiting_confirmation"}


def _build_initial_state(snapshot) -> dict:
    """把数据库运行快照转换为 Graph State。"""

    return {
        "task_id": snapshot.task_id,
        "job_id": snapshot.job_id,
        "resume_version_id": snapshot.resume_profile["resume_version_id"],
        "job_description": snapshot.job_description,
        "resume_text": snapshot.resume_profile["raw_text"],
        "conversation_context": snapshot.conversation_context,
        "system_prompt": JOBFIT_PERSISTED_SYSTEM_PROMPT,
        "max_steps": snapshot.max_steps,
        "trace": [],
    }


def _build_runtime_context(
    *,
    snapshot,
    session_factory: async_sessionmaker[AsyncSession],
    rag_enabled: bool,
    event_sink: AgentEventSink | None,
) -> JobFitGraphContext:
    """构造不进入 Checkpoint 的运行时依赖。"""

    registry = build_jobfit_tool_registry()

    def tool_context_factory(state: dict, step: int) -> ToolContext:
        return ToolContext(
            current_user=CurrentUser(
                id=snapshot.user_id,
                username=snapshot.username,
                role=snapshot.role,
            ),
            session_factory=session_factory,
            task_id=snapshot.task_id,
            step_no=step,
            resume_profile_snapshot=snapshot.resume_profile,
            resume_version_id=snapshot.resume_profile[
                "resume_version_id"
            ],
            rag_enabled=rag_enabled,
            event_sink=event_sink,
            defer_report_save=True,
            collect_tool_audit=True,
        )

    return JobFitGraphContext(
        chat_with_tools=chat_with_tools,
        tool_registry=registry,
        tool_context_factory=tool_context_factory,
        event_sink=event_sink,
    )


def _fallback_report(graph_result: dict) -> dict:
    """Graph 没有 pending report 时生成安全回退报告。"""

    return {
        "summary": (
            graph_result.get("final_answer")
            or "ReAct 达到最大步数，未生成最终回答。"
        ),
        "result_json": {
            "react_status": (
                graph_result.get("react_status") or "max_steps_reached"
            ),
            "answer": graph_result.get("final_answer"),
            "steps": graph_result.get("current_step", 0),
            "trace": graph_result.get("tool_trace", []),
            "usage": graph_result.get("usage", {}),
        },
    }


def _build_graph_metrics(
    graph_result: dict,
    *,
    total_ms: int,
) -> dict:
    """把 Graph State 中的指标整理为数据库 JSON。"""

    usage_records = [
        UsageRecord.model_validate(item)
        for item in graph_result.get("usage_records", [])
    ]
    cost = summarize_usage_cost(usage_records)
    metrics = build_task_metrics(
        request_id=get_request_id(),
        total_ms=total_ms,
        model_ms=graph_result.get("model_ms", 0),
        tool_ms=graph_result.get("tool_ms", 0),
        steps=graph_result.get("current_step", 0),
        usage=graph_result.get("usage", {}),
        node_metrics=graph_result.get("node_metrics", []),
        error_code=graph_result.get("error_code"),
        estimated_cost=cost.estimated_cost,
        currency=cost.currency,
        usage_call_count=cost.calls,
        usage_by_model={
            model: aggregate.model_dump(mode="json")
            for model, aggregate in cost.by_model.items()
        },
    )
    return metrics.model_dump(mode="json")


async def _persist_waiting_confirmation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    task_id: int,
    current_step: int,
    pending_confirmation: dict | None,
    usage: dict | None,
    metrics_json: dict,
    request_id: str | None,
) -> GraphTaskExecutionResult:
    """保存等待人工确认状态。"""

    async with session_factory() as session:
        async with session.begin():
            task = await mark_analysis_task_waiting_confirmation(
                session,
                user_id=user_id,
                task_id=task_id,
                current_step=current_step,
                current_node="human_confirmation",
                metrics_json=metrics_json,
                last_request_id=request_id,
            )

    return GraphTaskExecutionResult(
        task_id=task.task_id,
        status=task.status,
        current_node=task.current_node,
        current_step=current_step,
        interrupted=True,
        pending_confirmation=pending_confirmation,
        usage=usage,
    )


async def _persist_graph_completion(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    snapshot,
    graph_result: dict,
    metrics_json: dict,
    request_id: str | None,
) -> GraphTaskExecutionResult:
    """在人工确认后保存报告、简历版本和任务终态。"""

    decision = graph_result.get("confirmation_decision")
    current_step = min(
        max(graph_result.get("current_step", 0), 0),
        snapshot.max_steps,
    )

    if graph_result.get("status") == "cancelled" or decision == "reject":
        async with session_factory() as session:
            async with session.begin():
                events = [
                    ToolAuditEvent.model_validate(event)
                    for event in graph_result.get(
                        "tool_audit_events",
                        [],
                    )
                ]
                if events:
                    await persist_tool_audit_events(
                        session,
                        user_id=snapshot.user_id,
                        task_id=snapshot.task_id,
                        events=events,
                    )
                task = await complete_analysis_task(
                    session,
                    user_id=snapshot.user_id,
                    task_id=snapshot.task_id,
                    status="cancelled",
                    current_step=current_step,
                    error_code="user_rejected",
                    current_node="cancel",
                    metrics_json=metrics_json,
                    last_request_id=request_id,
                )
        return GraphTaskExecutionResult(
            task_id=task.task_id,
            status=task.status,
            current_node=task.current_node,
            current_step=current_step,
        )

    report_payload = (
        graph_result.get("reviewed_report")
        or graph_result.get("pending_report")
    )
    if not isinstance(report_payload, dict):
        report_payload = _fallback_report(graph_result)

    summary = str(report_payload.get("summary") or "").strip()
    result_json = report_payload.get("result_json")
    if not summary or not isinstance(result_json, dict):
        raise ValueError("Graph 报告结构不合法")

    resume_revision_text = graph_result.get("resume_revision_text")
    new_resume_version_id = None

    async with session_factory() as session:
        async with session.begin():
            task_repository = AnalysisTaskRepository(session)
            task = await task_repository.get_for_user(
                task_id=snapshot.task_id,
                user_id=snapshot.user_id,
                for_update=True,
            )
            if task is None:
                raise LookupError("任务不存在或无权访问")

            events = [
                ToolAuditEvent.model_validate(event)
                for event in graph_result.get("tool_audit_events", [])
            ]
            if events:
                await persist_tool_audit_events(
                    session,
                    user_id=snapshot.user_id,
                    task_id=snapshot.task_id,
                    events=events,
                )

            report = await ReportRepository(session).create_for_user(
                task_id=snapshot.task_id,
                user_id=snapshot.user_id,
                summary=summary,
                result_json=result_json,
                make_current=True,
            )

            if (
                decision == "revise"
                and isinstance(resume_revision_text, str)
                and resume_revision_text.strip()
            ):
                resume_version = await ResumeVersionRepository(
                    session
                ).create_next_for_user(
                    resume_id=snapshot.resume_profile["resume_id"],
                    user_id=snapshot.user_id,
                    raw_text=resume_revision_text.strip(),
                    extracted_sections=None,
                    source_type="text",
                )
                new_resume_version_id = resume_version.resume_version_id

            task = await complete_analysis_task(
                session,
                user_id=snapshot.user_id,
                task_id=snapshot.task_id,
                status="completed",
                current_step=current_step,
                current_node="finalize",
                metrics_json=metrics_json,
                last_request_id=request_id,
            )

    return GraphTaskExecutionResult(
        task_id=task.task_id,
        status=task.status,
        current_node=task.current_node,
        current_step=current_step,
        final_answer=graph_result.get("final_answer"),
        usage=graph_result.get("usage"),
        report_id=report.report_id,
        report_version=report.version_no,
        new_resume_version_id=new_resume_version_id,
    )


async def _execute_graph_task(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    task_id: int,
    redis_client: Redis | None,
    event_sink: AgentEventSink | None,
    resume_payload: dict | None,
) -> GraphTaskExecutionResult:
    """执行或恢复 Graph 任务，并维护 Redis 运行锁。"""

    owner_token = uuid4().hex
    lock_acquired = False
    snapshot = None
    task_token = set_task_id(task_id)

    if redis_client is not None:
        try:
            lock_acquired = await acquire_task_run_lock(
                redis_client,
                task_id=task_id,
                owner_token=owner_token,
            )
            if not lock_acquired:
                raise TaskStateConflictError("任务正在执行")
        except TaskStateConflictError:
            raise
        except RedisError:
            logger.warning(
                "获取 Graph 任务运行锁失败，继续使用数据库状态保护 task_id=%s",
                task_id,
                exc_info=True,
            )

    try:
        started_at = perf_counter()
        is_resume = resume_payload is not None
        snapshot = await _prepare_run_snapshot(
            session_factory,
            user_id=user_id,
            task_id=task_id,
            allowed_statuses=(
                RESUMABLE_GRAPH_STATUSES
                if is_resume
                else RUNNABLE_GRAPH_START_STATUSES
            ),
            increment_attempt=not is_resume,
        )

        await _cache_run_status_safely(
            redis_client,
            user_id=user_id,
            task_id=task_id,
            status="running",
            current_step=snapshot.previous_current_step,
            attempt=snapshot.attempt,
            max_steps=snapshot.max_steps,
            current_node=None,
        )

        await _emit_event(
            event_sink,
            AgentEvent(
                type="graph_started",
                task_id=task_id,
                data={
                    "attempt": snapshot.attempt,
                    "resume": is_resume,
                },
            ),
        )
        await _emit_event(
            event_sink,
            AgentEvent(
                type="task_started",
                task_id=task_id,
                data={
                    "status": "running",
                    "attempt": snapshot.attempt,
                    "max_steps": snapshot.max_steps,
                    "engine": "langgraph",
                },
            ),
        )

        rag_enabled = False
        if not is_resume:
            rag_enabled = await _prepare_rag_safely(
                session_factory,
                user_id=snapshot.user_id,
                task_id=snapshot.task_id,
                resume_version_id=snapshot.resume_profile[
                    "resume_version_id"
                ],
                event_sink=event_sink,
            )

        runtime_context = _build_runtime_context(
            snapshot=snapshot,
            session_factory=session_factory,
            rag_enabled=rag_enabled,
            event_sink=event_sink,
        )
        config = build_checkpoint_config(
            snapshot.task_id,
            snapshot.attempt,
        )

        async with open_postgres_checkpointer() as saver:
            graph = build_jobfit_graph(checkpointer=saver)

            if is_resume:
                await _emit_event(
                    event_sink,
                    AgentEvent(
                        type="resumed",
                        task_id=task_id,
                        data={"attempt": snapshot.attempt},
                    ),
                )
                checkpoint_state = await graph.aget_state(config)
                if not checkpoint_state.next:
                    raise TaskStateConflictError(
                        "任务没有等待恢复的节点"
                    )
                graph_result = await graph.ainvoke(
                    Command(resume=resume_payload),
                    config=config,
                    context=runtime_context,
                )
            else:
                graph_result = await graph.ainvoke(
                    _build_initial_state(snapshot),
                    config=config,
                    context=runtime_context,
                )

        total_ms = round((perf_counter() - started_at) * 1000)
        request_id = get_request_id()
        metrics_json = _build_graph_metrics(
            graph_result,
            total_ms=total_ms,
        )

        if "__interrupt__" in graph_result:
            result = await _persist_waiting_confirmation(
                session_factory,
                user_id=snapshot.user_id,
                task_id=snapshot.task_id,
                current_step=graph_result.get("current_step", 0),
                pending_confirmation=graph_result.get(
                    "pending_report"
                ),
                usage=graph_result.get("usage"),
                metrics_json=metrics_json,
                request_id=request_id,
            )
        else:
            result = await _persist_graph_completion(
                session_factory,
                snapshot=snapshot,
                graph_result=graph_result,
                metrics_json=metrics_json,
                request_id=request_id,
            )

        await _cache_run_status_safely(
            redis_client,
            user_id=user_id,
            task_id=task_id,
            status=result.status,
            current_step=result.current_step,
            attempt=snapshot.attempt,
            max_steps=snapshot.max_steps,
            current_node=result.current_node,
        )

        if result.status == "completed":
            await _emit_event(
                event_sink,
                AgentEvent(
                    type="task_completed",
                    task_id=task_id,
                    content=result.final_answer,
                    data={
                        "status": result.status,
                        "report_id": result.report_id,
                        "current_node": result.current_node,
                        "usage": result.usage or {},
                    },
                ),
            )
        elif result.status == "cancelled":
            await _emit_event(
                event_sink,
                AgentEvent(
                    type="cancelled",
                    task_id=task_id,
                    data={"status": result.status},
                ),
            )
        return result
    except asyncio.CancelledError:
        await _persist_failure_state(
            session_factory,
            user_id=user_id,
            task_id=task_id,
            events=[],
            error_code="client_disconnected",
            interrupted=True,
            pending_report=None,
        )
        await _emit_event(
            event_sink,
            AgentEvent(
                type="task_interrupted",
                task_id=task_id,
                data={"error_code": "client_disconnected"},
            ),
        )
        raise
    except Exception as exc:
        failed_interrupted = isinstance(exc, LLMServiceError)
        failure_status = await _persist_failure_state(
            session_factory,
            user_id=user_id,
            task_id=task_id,
            events=[],
            error_code=(
                "llm_service_error"
                if failed_interrupted
                else "graph_execution_failed"
            ),
            interrupted=failed_interrupted,
            pending_report=None,
        )
        resolved_status = (
            failure_status
            or ("interrupted" if failed_interrupted else "failed")
        )
        if snapshot is not None:
            await _cache_run_status_safely(
                redis_client,
                user_id=user_id,
                task_id=task_id,
                status=resolved_status,
                current_step=snapshot.previous_current_step,
                attempt=snapshot.attempt,
                max_steps=snapshot.max_steps,
            )
        await _emit_event(
            event_sink,
            AgentEvent(
                type=(
                    "task_interrupted"
                    if resolved_status == "interrupted"
                    else "task_failed"
                ),
                task_id=task_id,
                data={
                    "error_code": (
                        "llm_service_error"
                        if failed_interrupted
                        else "graph_execution_failed"
                    )
                },
            ),
        )
        raise
    finally:
        reset_task_id(task_token)
        if redis_client is not None and lock_acquired:
            try:
                await release_task_run_lock(
                    redis_client,
                    task_id=task_id,
                    owner_token=owner_token,
                )
            except RedisError:
                logger.warning(
                    "释放 Graph 任务运行锁失败 task_id=%s",
                    task_id,
                    exc_info=True,
                )


async def run_graph_persisted_task(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    task_id: int,
    redis_client: Redis | None = None,
    event_sink: AgentEventSink | None = None,
) -> GraphTaskExecutionResult:
    """创建一次新的 LangGraph 持久化任务运行。"""

    return await _execute_graph_task(
        session_factory,
        user_id=user_id,
        task_id=task_id,
        redis_client=redis_client,
        event_sink=event_sink,
        resume_payload=None,
    )


async def resume_graph_persisted_task(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    task_id: int,
    decision: str,
    edited_report: dict | None = None,
    resume_revision_text: str | None = None,
    redis_client: Redis | None = None,
    event_sink: AgentEventSink | None = None,
) -> GraphTaskExecutionResult:
    """提交人工确认并恢复 LangGraph 持久化任务。"""

    payload = {"decision": decision}
    if edited_report is not None:
        payload["edited_report"] = edited_report
    if resume_revision_text is not None:
        payload["resume_revision_text"] = resume_revision_text

    return await _execute_graph_task(
        session_factory,
        user_id=user_id,
        task_id=task_id,
        redis_client=redis_client,
        event_sink=event_sink,
        resume_payload=payload,
    )


async def get_graph_task_confirmation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    task_id: int,
) -> GraphTaskExecutionResult:
    """读取当前任务的待确认报告。"""

    async with session_factory() as session:
        task = await AnalysisTaskRepository(session).get_for_user(
            task_id=task_id,
            user_id=user_id,
        )
        if task is None:
            raise LookupError("任务不存在或无权访问")

        if task.status != "waiting_confirmation":
            return GraphTaskExecutionResult(
                task_id=task.task_id,
                status=task.status,
                current_node=task.current_node,
                current_step=task.current_step,
            )

        config = build_checkpoint_config(
            task.task_id,
            task.attempt,
        )

    async with open_postgres_checkpointer() as saver:
        graph = build_jobfit_graph(checkpointer=saver)
        checkpoint_state = await graph.aget_state(config)
        return GraphTaskExecutionResult(
            task_id=task.task_id,
            status=task.status,
            current_node=task.current_node,
            current_step=task.current_step,
            interrupted=True,
            pending_confirmation=checkpoint_state.values.get(
                "pending_report"
            ),
        )


__all__ = [
    "get_graph_task_confirmation",
    "resume_graph_persisted_task",
    "run_graph_persisted_task",
]
