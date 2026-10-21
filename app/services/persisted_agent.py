# 组合数据库任务、ReAct Agent 和结果持久化。

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.cache.task_state import (
    acquire_task_run_lock,
    cache_task_status,
    release_task_run_lock,
)
from app.core.exceptions import LLMServiceError, TaskStateConflictError
from app.core.cost_tracking import (
    finish_usage_collection,
    start_usage_collection,
    summarize_usage_cost,
)
from app.core.observability import (
    build_task_metrics,
    get_request_id,
    reset_task_id,
    set_task_id,
)
from app.db.models import AnalysisTask
from app.repositories import (
    AnalysisTaskRepository,
    JobRepository,
    MessageRepository,
    ReportRepository,
    ResumeRepository,
    ResumeVersionRepository,
    UserRepository,
)
from app.schemas.agent_events import AgentEvent, AgentEventSink
from app.schemas.agent_run import AnalysisTaskRunSnapshot
from app.schemas.analysis_task_api import PersistedAgentExecutionResult
from app.schemas.auth import CurrentUser
from app.schemas.tool_audit import ToolAuditEvent
from app.services.analysis_results import (
    complete_analysis_task,
    mark_analysis_task_failed,
    mark_analysis_task_interrupted,
    persist_tool_audit_events,
)
from app.services.analysis_tasks import create_analysis_task
from app.services.conversation_context import (
    build_compressed_conversation_context,
)
from app.services.rag_evidence import prepare_resume_rag
from app.services.react_agent import (
    JOBFIT_PERSISTED_SYSTEM_PROMPT,
    build_jobfit_react_messages,
    run_react_loop,
)
from app.tools import ToolContext
from app.tools.jobfit import build_jobfit_tool_registry


logger = logging.getLogger(__name__)
RUNNABLE_TASK_STATUSES = {"pending", "interrupted"}


async def _cache_run_status_safely(
    redis_client: Redis | None,
    *,
    user_id: int,
    task_id: int,
    status: str,
    current_step: int,
    attempt: int,
    max_steps: int,
    current_node: str | None = None,
) -> None:
    if redis_client is None:
        return

    try:
        await cache_task_status(
            redis_client,
            user_id=user_id,
            task_id=task_id,
            status=status,
            current_step=current_step,
            attempt=attempt,
            max_steps=max_steps,
            current_node=current_node,
        )
    except RedisError:
        logger.warning(
            "更新任务状态缓存失败 task_id=%s status=%s",
            task_id,
            status,
            exc_info=True,
        )


async def _emit_event(
    event_sink: AgentEventSink | None,
    event: AgentEvent,
) -> None:
    if event_sink is not None:
        await event_sink(event)


async def create_persisted_task(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
    resume_version_id: int,
    conversation_id: int | None,
) -> AnalysisTask:
    """创建 pending 分析任务，不提交事务。"""

    return await create_analysis_task(
        session,
        user_id=user_id,
        job_id=job_id,
        resume_version_id=resume_version_id,
        conversation_id=conversation_id,
    )


async def _prepare_run_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    task_id: int,
    allowed_statuses: set[str] | None = None,
    increment_attempt: bool = True,
) -> AnalysisTaskRunSnapshot:
    """用短事务锁定任务并提交 running 状态与运行快照。"""

    async with session_factory() as session:
        async with session.begin():
            task_repository = AnalysisTaskRepository(session)
            job_repository = JobRepository(session)
            version_repository = ResumeVersionRepository(session)
            resume_repository = ResumeRepository(session)
            user_repository = UserRepository(session)

            task = await task_repository.get_for_user(
                task_id=task_id,
                user_id=user_id,
                for_update=True,
            )
            if task is None:
                raise LookupError("任务不存在或无权访问")

            if task.status not in (
                allowed_statuses or RUNNABLE_TASK_STATUSES
            ):
                raise TaskStateConflictError(
                    f"任务状态 {task.status} 不允许执行"
                )

            user = await user_repository.get_by_id(user_id)
            job = await job_repository.get_for_user(
                job_id=task.job_id,
                user_id=user_id,
                for_update=True,
            )
            resume_version = await version_repository.get_for_user(
                resume_version_id=task.resume_version_id,
                user_id=user_id,
                for_update=True,
            )

            if (
                user is None
                or job is None
                or resume_version is None
            ):
                raise LookupError("任务关联资源不存在或无权访问")

            resume = await resume_repository.get_for_user(
                resume_id=resume_version.resume_id,
                user_id=user_id,
            )
            if resume is None:
                raise LookupError("任务关联资源不存在或无权访问")

            conversation_context = None
            if task.conversation_id is not None:
                recent_messages = await MessageRepository(
                    session
                ).list_recent_for_user(
                    conversation_id=task.conversation_id,
                    user_id=user_id,
                )
                conversation_context = (
                    build_compressed_conversation_context(
                        recent_messages
                    )
                    or None
                )

            previous_current_step = task.current_step
            previous_status = task.status
            if (
                previous_status == "pending"
                or task.started_at is None
            ):
                task.started_at = datetime.now(timezone.utc)
            task.status = "running"
            if increment_attempt:
                task.attempt += 1
            task.finished_at = None
            task.error_code = None
            task.error_message_safe = None
            await session.flush()

            resume_profile = {
                "found": True,
                "task_id": task.task_id,
                "resume_id": resume.resume_id,
                "resume_version_id": resume_version.resume_version_id,
                "version_no": resume_version.version_no,
                "resume_title": resume.title,
                "raw_text": resume_version.raw_text,
                "extracted_sections": resume_version.extracted_sections,
            }

            return AnalysisTaskRunSnapshot(
                task_id=task.task_id,
                user_id=user.user_id,
                username=user.username,
                role=user.role,
                job_id=job.job_id,
                job_description=job.raw_description,
                resume_profile=resume_profile,
                conversation_id=task.conversation_id,
                conversation_context=conversation_context,
                max_steps=task.max_steps,
                previous_current_step=previous_current_step,
                attempt=task.attempt,
                started_at=task.started_at,
            )


async def _persist_failure_state(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    task_id: int,
    events: list[ToolAuditEvent],
    error_code: str,
    interrupted: bool,
    pending_report: dict | None,
) -> str | None:
    """用新事务保存审计和失败或中断状态。"""

    try:
        async with session_factory() as session:
            async with session.begin():
                task_repository = AnalysisTaskRepository(session)
                task = await task_repository.get_for_user(
                    task_id=task_id,
                    user_id=user_id,
                    for_update=True,
                )
                if task is None:
                    return None

                await persist_tool_audit_events(
                    session,
                    user_id=user_id,
                    task_id=task_id,
                    events=events,
                )

                if interrupted and task.status == "running":
                    fallback_summary = (
                        pending_report["summary"]
                        if pending_report is not None
                        else "Agent 执行中断，可重试。"
                    )
                    fallback_result = (
                        pending_report["result_json"]
                        if pending_report is not None
                        else {
                            "status": "interrupted",
                            "error_code": error_code,
                        }
                    )
                    await ReportRepository(session).create_for_user(
                        task_id=task_id,
                        user_id=user_id,
                        summary=fallback_summary,
                        result_json=fallback_result,
                        make_current=True,
                    )
                    task = await mark_analysis_task_interrupted(
                        session,
                        user_id=user_id,
                        task_id=task_id,
                        error_code=error_code,
                    )
                elif not interrupted:
                    task = await mark_analysis_task_failed(
                        session,
                        user_id=user_id,
                        task_id=task_id,
                        error_code=error_code,
                    )
                return task.status
    except Exception:
        logger.exception(
            "保存任务失败状态时发生错误 task_id=%s",
            task_id,
        )
        return None

async def _prepare_rag_safely(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    task_id: int,
    resume_version_id: int,
    event_sink: AgentEventSink | None,
) -> bool:
    """准备 RAG 索引，失败时允许 Agent 回退旧关键词路径。"""

    await _emit_event(
        event_sink,
        AgentEvent(
            type="index_started",
            task_id=task_id,
            data={"resume_version_id": resume_version_id},
        ),
    )

    try:
        async with session_factory() as session:
            async with session.begin():
                await prepare_resume_rag(
                    session,
                    user_id=user_id,
                    resume_version_id=resume_version_id,
                )
    except Exception:
        logger.warning(
            "准备 RAG 索引失败，回退旧检索 task_id=%s",
            task_id,
            exc_info=True,
        )
        await _emit_event(
            event_sink,
            AgentEvent(
                type="index_failed",
                task_id=task_id,
                data={"error_code": "rag_index_failed"},
            ),
        )
        return False

    await _emit_event(
        event_sink,
        AgentEvent(
            type="index_finished",
            task_id=task_id,
            data={"resume_version_id": resume_version_id},
        ),
    )
    return True

def _build_react_metrics(
    react_result,
    audit_events,
    usage_records,
    *,
    error_code: str | None = None,
) -> dict:
    cost = summarize_usage_cost(usage_records)
    metrics = build_task_metrics(
        request_id=get_request_id(),
        total_ms=react_result.latency_ms,
        model_ms=react_result.latency_ms,
        tool_ms=sum(
            event.duration_ms or 0
            for event in audit_events
        ),
        steps=react_result.steps,
        usage=react_result.usage.model_dump(mode="json"),
        error_code=error_code,
        estimated_cost=cost.estimated_cost,
        currency=cost.currency,
        usage_call_count=cost.calls,
        usage_by_model={
            model: aggregate.model_dump(mode="json")
            for model, aggregate in cost.by_model.items()
        },
    )
    return metrics.model_dump(mode="json")


async def _run_persisted_task_core(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    task_id: int,
    redis_client: Redis | None = None,
    event_sink: AgentEventSink | None = None,
) -> PersistedAgentExecutionResult:
    """按三段事务边界执行持久化 Agent。"""

    snapshot = await _prepare_run_snapshot(
        session_factory,
        user_id=user_id,
        task_id=task_id,
    )
    await _cache_run_status_safely(
        redis_client,
        user_id=user_id,
        task_id=task_id,
        status="running",
        current_step=snapshot.previous_current_step,
        attempt=snapshot.attempt,
        max_steps=snapshot.max_steps,
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
            },
        ),
    )

    rag_enabled = await _prepare_rag_safely(
        session_factory,
        user_id=snapshot.user_id,
        task_id=snapshot.task_id,
        resume_version_id=snapshot.resume_profile[
            "resume_version_id"
        ],
        event_sink=event_sink,
    )

    context = ToolContext(
        current_user=CurrentUser(
            id=snapshot.user_id,
            username=snapshot.username,
            role=snapshot.role,
        ),
        session_factory=session_factory,
        task_id=snapshot.task_id,
        step_no=snapshot.previous_current_step,
        resume_profile_snapshot=snapshot.resume_profile,
        resume_version_id=snapshot.resume_profile[
            "resume_version_id"
        ],
        rag_enabled=rag_enabled,
        event_sink=event_sink,
        defer_report_save=True,
        collect_tool_audit=True,
    )

    usage_token = start_usage_collection()
    try:
        react_result = await run_react_loop(
            messages=build_jobfit_react_messages(
                job_description=snapshot.job_description,
                resume_text=None,
                system_prompt=JOBFIT_PERSISTED_SYSTEM_PROMPT,
                conversation_context=snapshot.conversation_context,
            ),
            registry=build_jobfit_tool_registry(),
            context=context,
            max_steps=snapshot.max_steps,
            event_sink=event_sink,
        )
    except asyncio.CancelledError:
        finish_usage_collection(usage_token)
        await _persist_failure_state(
            session_factory,
            user_id=user_id,
            task_id=task_id,
            events=context.tool_audit_events,
            error_code="client_disconnected",
            interrupted=True,
            pending_report=context.pending_report,
        )
        await _cache_run_status_safely(
            redis_client,
            user_id=user_id,
            task_id=task_id,
            status="interrupted",
            current_step=snapshot.previous_current_step,
            attempt=snapshot.attempt,
            max_steps=snapshot.max_steps,
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
        finish_usage_collection(usage_token)
        failed_interrupted = isinstance(exc, LLMServiceError)
        failure_status = await _persist_failure_state(
            session_factory,
            user_id=user_id,
            task_id=task_id,
            events=context.tool_audit_events,
            error_code=(
                "llm_service_error"
                if failed_interrupted
                else "agent_execution_failed"
            ),
            interrupted=failed_interrupted,
            pending_report=context.pending_report,
        )
        resolved_status = (
            failure_status
            or ("interrupted" if failed_interrupted else "failed")
        )
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
                        else "agent_execution_failed"
                    )
                },
            ),
        )
        raise

    usage_records = finish_usage_collection(usage_token)

    try:
        async with session_factory() as session:
            async with session.begin():
                task_repository = AnalysisTaskRepository(session)
                report_repository = ReportRepository(session)

                task = await task_repository.get_for_user(
                    task_id=task_id,
                    user_id=user_id,
                    for_update=True,
                )
                if task is None:
                    raise LookupError("任务不存在或无权访问")

                if task.status != "running":
                    raise TaskStateConflictError(
                        f"任务状态 {task.status} 不允许保存结果"
                    )

                await persist_tool_audit_events(
                    session,
                    user_id=user_id,
                    task_id=task_id,
                    events=context.tool_audit_events,
                )

                fallback_result = {
                    "react_status": react_result.status,
                    "answer": react_result.answer,
                    "steps": react_result.steps,
                    "trace": [
                        item.model_dump(mode="json")
                        for item in react_result.trace
                    ],
                    "usage": react_result.usage.model_dump(mode="json"),
                    "latency_ms": react_result.latency_ms,
                }

                if context.pending_report is not None:
                    summary = context.pending_report["summary"]
                    result_json = context.pending_report["result_json"]
                else:
                    summary = (
                        react_result.answer
                        or "ReAct 达到最大步数，未生成最终回答。"
                    )
                    result_json = fallback_result

                report = await report_repository.create_for_user(
                    task_id=task.task_id,
                    user_id=user_id,
                    summary=summary,
                    result_json=result_json,
                    make_current=True,
                )

                if snapshot.conversation_id is not None and react_result.answer:
                    await MessageRepository(session).create_for_user(
                        conversation_id=snapshot.conversation_id,
                        user_id=user_id,
                        role="assistant",
                        content=react_result.answer,
                        message_metadata={
                            "task_id": task.task_id,
                            "report_id": report.report_id,
                        },
                    )

                if react_result.status == "completed":
                    task_status = "completed"
                    current_step = min(
                        react_result.steps,
                        task.max_steps,
                    )
                    error_code = None
                else:
                    task_status = "interrupted"
                    current_step = task.max_steps
                    error_code = "max_steps_reached"

                task = await complete_analysis_task(
                    session,
                    user_id=user_id,
                    task_id=task_id,
                    status=task_status,
                    current_step=current_step,
                    error_code=error_code,
                    metrics_json=_build_react_metrics(
                        react_result,
                        context.tool_audit_events,
                        usage_records,
                        error_code=error_code,
                    ),
                    last_request_id=get_request_id(),
                )

                await session.commit()
                await _cache_run_status_safely(
                    redis_client,
                    user_id=user_id,
                    task_id=task_id,
                    status=task.status,
                    current_step=task.current_step,
                    attempt=task.attempt,
                    max_steps=task.max_steps,
                )
                await _emit_event(
                    event_sink,
                    AgentEvent(
                        type=(
                            "task_completed"
                            if task.status == "completed"
                            else "task_interrupted"
                        ),
                        task_id=task.task_id,
                        content=react_result.answer,
                        data={
                            "status": task.status,
                            "steps": react_result.steps,
                            "attempt": task.attempt,
                            "report_id": report.report_id,
                            "report_version": report.version_no,
                            "usage": react_result.usage.model_dump(
                                mode="json"
                            ),
                            "latency_ms": react_result.latency_ms,
                        },
                    ),
                )
                return PersistedAgentExecutionResult(
                    task_id=task.task_id,
                    status=task.status,
                    answer=react_result.answer,
                    steps=react_result.steps,
                    max_steps=react_result.max_steps,
                    usage=react_result.usage,
                    latency_ms=react_result.latency_ms,
                    report_id=report.report_id,
                    report_version=report.version_no,
                )
    except asyncio.CancelledError:
        await _persist_failure_state(
            session_factory,
            user_id=user_id,
            task_id=task_id,
            events=context.tool_audit_events,
            error_code="client_disconnected",
            interrupted=True,
            pending_report=context.pending_report,
        )
        await _cache_run_status_safely(
            redis_client,
            user_id=user_id,
            task_id=task_id,
            status="interrupted",
            current_step=snapshot.previous_current_step,
            attempt=snapshot.attempt,
            max_steps=snapshot.max_steps,
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
            events=context.tool_audit_events,
            error_code=(
                "llm_service_error"
                if failed_interrupted
                else "agent_execution_failed"
            ),
            interrupted=failed_interrupted,
            pending_report=context.pending_report,
        )
        resolved_status = (
            failure_status
            or ("interrupted" if failed_interrupted else "failed")
        )
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
                        else "agent_execution_failed"
                    )
                },
            ),
        )
        raise


async def run_persisted_task(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    task_id: int,
    redis_client: Redis | None = None,
    event_sink: AgentEventSink | None = None,
) -> PersistedAgentExecutionResult:
    """在可选 Redis 运行锁下执行持久化 Agent。"""

    owner_token = uuid4().hex
    lock_acquired = False
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
                "获取任务运行锁失败，继续使用数据库状态保护 task_id=%s",
                task_id,
                exc_info=True,
            )

    try:
        return await _run_persisted_task_core(
            session_factory,
            user_id=user_id,
            task_id=task_id,
            redis_client=redis_client,
            event_sink=event_sink,
        )
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
                    "释放任务运行锁失败 task_id=%s",
                    task_id,
                    exc_info=True,
                )

__all__ = [
    "RUNNABLE_TASK_STATUSES",
    "create_persisted_task",
    "run_persisted_task",
]
