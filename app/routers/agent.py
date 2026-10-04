# 提供 JobFit ReAct Agent 的 HTTP 接口。

import asyncio
import logging
from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.client import get_redis_client
from app.cache.task_state import (
    cache_task_status,
    get_cached_task_status,
)
from app.core.exceptions import TaskStateConflictError
from app.core.response import success_response
from app.dependencies.auth import get_current_user
from app.dependencies.rate_limit import make_rate_limit_dependency
from app.dependencies.database import get_db_session
from app.db.session import async_session_factory
from app.repositories import AnalysisTaskRepository, ReportRepository
from app.schemas.agent_events import AgentEvent, format_sse_event
from app.schemas.analysis_task_api import (
    AnalysisTaskCreateRequest,
    AnalysisTaskResponse,
    AnalysisTaskSummary,
    GraphTaskConfirmationRequest,
    ReportResponse,
)
from app.schemas.auth import CurrentUser
from app.schemas.react_agent import JobFitAgentRequest
from app.services.graph_agent import (
    get_graph_task_confirmation,
    resume_graph_persisted_task,
    run_graph_persisted_task,
)
from app.services.persisted_agent import (
    create_persisted_task,
    run_persisted_task,
)
from app.services.rate_limit import record_daily_token_usage
from app.services.react_agent import run_jobfit_agent
from app.tools import ToolContext


router = APIRouter(prefix="/api/agent", tags=["agent"])
logger = logging.getLogger(__name__)


def _preview(text: str, limit: int = 200) -> str:
    compact = " ".join(text.split())
    return compact[:limit]


def _current_report(task):
    reports = getattr(task, "reports", None) or []
    for report in reversed(reports):
        if report.deleted_at is None:
            return report
    return None


def _task_summary(task) -> AnalysisTaskSummary:
    report = _current_report(task)
    job = task.job
    resume_version = task.resume_version
    return AnalysisTaskSummary(
        task_id=task.task_id,
        job_id=task.job_id,
        resume_version_id=task.resume_version_id,
        conversation_id=task.conversation_id,
        job_title=job.title,
        company_name=job.company_name,
        job_description_preview=_preview(job.raw_description),
        resume_title=resume_version.resume.title,
        status=task.status,
        current_step=task.current_step,
        attempt=task.attempt,
        max_steps=task.max_steps,
        current_node=task.current_node,
        report_id=report.report_id if report else None,
        report_version=report.version_no if report else None,
        metrics_json=task.metrics_json,
        started_at=task.started_at,
        finished_at=task.finished_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _report_response(report) -> ReportResponse:
    return ReportResponse(
        report_id=report.report_id,
        task_id=report.task_id,
        version_no=report.version_no,
        is_current=report.is_current,
        summary=report.summary,
        result_json=report.result_json,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_analysis_task_endpoint(
    request: AnalysisTaskCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("tasks_create")
    ),
) -> JSONResponse:
    """创建当前用户的持久化岗位分析任务。"""

    try:
        async with session.begin():
            task = await create_persisted_task(
                session,
                user_id=current_user.id,
                job_id=request.job_id,
                resume_version_id=request.resume_version_id,
                conversation_id=request.conversation_id,
            )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    try:
        await cache_task_status(
            get_redis_client(),
            user_id=current_user.id,
            task_id=task.task_id,
            status=task.status,
            current_step=task.current_step,
            attempt=task.attempt,
            max_steps=task.max_steps,
            current_node=task.current_node,
        )
    except RedisError:
        logger.warning(
            "缓存新建任务状态失败 task_id=%s",
            task.task_id,
            exc_info=True,
        )

    data = AnalysisTaskResponse(
        task_id=task.task_id,
        status=task.status,
        current_step=task.current_step,
        attempt=task.attempt,
        max_steps=task.max_steps,
        current_node=task.current_node,
    )
    payload = success_response(data=data)
    payload["code"] = status.HTTP_201_CREATED
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=payload,
    )


@router.post("/tasks/{task_id}/run")
async def run_analysis_task_endpoint(
    task_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("agent_run")
    ),
) -> dict:
    """执行当前用户的持久化岗位分析任务。"""

    try:
        result = await run_persisted_task(
            async_session_factory,
            user_id=current_user.id,
            task_id=task_id,
            redis_client=get_redis_client(),
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except TaskStateConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    await record_daily_token_usage(
        get_redis_client(),
        user_id=current_user.id,
        total_tokens=result.usage.total_tokens,
    )
    return success_response(data=result)


@router.get("/tasks")
async def list_analysis_tasks_endpoint(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency(
            "tasks_list",
            enforce_token_quota=False,
            enforce_request_quota=False,
        )
    ),
) -> dict:
    """查询当前用户的历史分析任务。"""

    tasks = await AnalysisTaskRepository(session).list_for_user(
        current_user.id,
        with_relations=True,
    )
    return success_response(
        data=[_task_summary(task) for task in tasks]
    )


@router.get("/tasks/{task_id}")
async def get_analysis_task_endpoint(
    task_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency(
            "tasks_read",
            enforce_token_quota=False,
            enforce_request_quota=False,
        )
    ),
) -> dict:
    """优先从 Redis 获取当前用户的任务状态。"""

    redis = get_redis_client()

    try:
        cached = await get_cached_task_status(
            redis,
            user_id=current_user.id,
            task_id=task_id,
        )
    except RedisError:
        logger.warning(
            "读取任务状态缓存失败 task_id=%s",
            task_id,
            exc_info=True,
        )
        cached = None

    if cached is not None:
        data = AnalysisTaskResponse.model_validate(cached)
        return success_response(data=data)

    async with async_session_factory() as session:
        task = await AnalysisTaskRepository(session).get_for_user(
            task_id=task_id,
            user_id=current_user.id,
        )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在或无权访问",
        )

    data = AnalysisTaskResponse(
        task_id=task.task_id,
        status=task.status,
        current_step=task.current_step,
        attempt=task.attempt,
        max_steps=task.max_steps,
        current_node=task.current_node,
    )

    try:
        await cache_task_status(
            redis,
            user_id=current_user.id,
            task_id=task.task_id,
            status=task.status,
            current_step=task.current_step,
            attempt=task.attempt,
            max_steps=task.max_steps,
            current_node=task.current_node,
        )
    except RedisError:
        logger.warning(
            "回填任务状态缓存失败 task_id=%s",
            task.task_id,
            exc_info=True,
        )

    return success_response(data=data)


@router.get("/tasks/{task_id}/report")
async def get_analysis_task_report_endpoint(
    task_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(
        make_rate_limit_dependency(
            "task_report_read",
            enforce_token_quota=False,
            enforce_request_quota=False,
        )
    ),
) -> dict:
    """查询当前用户任务的当前版本报告。"""

    report = await ReportRepository(session).get_current_for_user(
        task_id=task_id,
        user_id=current_user.id,
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="报告不存在或尚未生成",
        )
    return success_response(data=_report_response(report))


@router.get("/tasks/{task_id}/stream")
async def stream_analysis_task_endpoint(
    task_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("agent_stream")
    ),
) -> StreamingResponse:
    """以 SSE 流式返回任务执行过程。"""

    async with async_session_factory() as session:
        task = await AnalysisTaskRepository(session).get_for_user(
            task_id=task_id,
            user_id=current_user.id,
        )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在或无权访问",
        )

    async def event_generator():
        queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        terminal_event_sent = False

        async def event_sink(event: AgentEvent) -> None:
            nonlocal terminal_event_sent
            if event.type in {
                "task_completed",
                "task_interrupted",
                "task_failed",
            }:
                terminal_event_sent = True
            if event.type == "task_completed":
                usage = event.data.get("usage") or {}
                total_tokens = int(
                    usage.get("total_tokens", 0)
                )
                await record_daily_token_usage(
                    get_redis_client(),
                    user_id=current_user.id,
                    total_tokens=total_tokens,
                )
            await queue.put(event)

        async def run_task() -> None:
            nonlocal terminal_event_sent
            try:
                await run_persisted_task(
                    async_session_factory,
                    user_id=current_user.id,
                    task_id=task_id,
                    redis_client=get_redis_client(),
                    event_sink=event_sink,
                )
            except asyncio.CancelledError:
                raise
            except TaskStateConflictError as exc:
                if not terminal_event_sent:
                    await queue.put(
                        AgentEvent(
                            type="error",
                            task_id=task_id,
                            content=str(exc),
                            data={"code": 409},
                        )
                    )
            except LookupError as exc:
                if not terminal_event_sent:
                    await queue.put(
                        AgentEvent(
                            type="error",
                            task_id=task_id,
                            content=str(exc),
                            data={"code": 404},
                        )
                    )
            except Exception:
                logger.exception(
                    "SSE 任务执行失败 task_id=%s",
                    task_id,
                )
                if not terminal_event_sent:
                    await queue.put(
                        AgentEvent(
                            type="error",
                            task_id=task_id,
                            content="任务执行失败",
                            data={"code": 500},
                        )
                    )
            finally:
                await queue.put(None)

        background_task = asyncio.create_task(run_task())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=15,
                    )
                except TimeoutError:
                    yield format_sse_event(
                        AgentEvent(
                            type="heartbeat",
                            task_id=task_id,
                        )
                    )
                    continue

                if event is None:
                    break

                yield format_sse_event(event)

            yield "event: done\ndata: [DONE]\n\n"
        finally:
            if not background_task.done():
                background_task.cancel()
                with suppress(asyncio.CancelledError):
                    await background_task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# 运行一次受控的 JobFit ReAct 分析。
@router.post("/tasks/{task_id}/graph/run")
async def run_graph_task_endpoint(
    task_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("graph_run")
    ),
) -> dict:
    """执行 LangGraph 版持久化岗位分析任务。"""

    try:
        result = await run_graph_persisted_task(
            async_session_factory,
            user_id=current_user.id,
            task_id=task_id,
            redis_client=get_redis_client(),
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except TaskStateConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return success_response(data=result)


@router.post("/tasks/{task_id}/graph/resume")
async def resume_graph_task_endpoint(
    task_id: int,
    request: GraphTaskConfirmationRequest,
    current_user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(
        make_rate_limit_dependency(
            "graph_resume",
            enforce_token_quota=False,
            enforce_request_quota=False,
        )
    ),
) -> dict:
    """提交人工确认并恢复 LangGraph 任务。"""

    try:
        result = await resume_graph_persisted_task(
            async_session_factory,
            user_id=current_user.id,
            task_id=task_id,
            decision=request.decision,
            edited_report=request.edited_report,
            resume_revision_text=request.resume_revision_text,
            redis_client=get_redis_client(),
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except TaskStateConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return success_response(data=result)


@router.get("/tasks/{task_id}/graph/confirmation")
async def get_graph_task_confirmation_endpoint(
    task_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(
        make_rate_limit_dependency(
            "graph_confirmation",
            enforce_token_quota=False,
            enforce_request_quota=False,
        )
    ),
) -> dict:
    """读取当前任务的待确认报告。"""

    try:
        result = await get_graph_task_confirmation(
            async_session_factory,
            user_id=current_user.id,
            task_id=task_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return success_response(data=result)


@router.get("/tasks/{task_id}/graph/stream")
async def stream_graph_task_endpoint(
    task_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("graph_stream")
    ),
) -> StreamingResponse:
    """以 SSE 流式执行 LangGraph 持久化任务。"""

    async with async_session_factory() as session:
        task = await AnalysisTaskRepository(session).get_for_user(
            task_id=task_id,
            user_id=current_user.id,
        )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在或无权访问",
        )

    async def event_generator():
        queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        terminal_event_sent = False

        async def event_sink(event: AgentEvent) -> None:
            nonlocal terminal_event_sent
            if event.type in {
                "task_completed",
                "task_interrupted",
                "task_failed",
                "cancelled",
                "waiting_confirmation",
            }:
                terminal_event_sent = True
            await queue.put(event)

        async def run_task() -> None:
            nonlocal terminal_event_sent
            try:
                await run_graph_persisted_task(
                    async_session_factory,
                    user_id=current_user.id,
                    task_id=task_id,
                    redis_client=get_redis_client(),
                    event_sink=event_sink,
                )
            except asyncio.CancelledError:
                raise
            except TaskStateConflictError as exc:
                if not terminal_event_sent:
                    await queue.put(
                        AgentEvent(
                            type="error",
                            task_id=task_id,
                            content=str(exc),
                            data={"code": 409},
                        )
                    )
            except LookupError as exc:
                if not terminal_event_sent:
                    await queue.put(
                        AgentEvent(
                            type="error",
                            task_id=task_id,
                            content=str(exc),
                            data={"code": 404},
                        )
                    )
            except Exception:
                logger.exception(
                    "Graph SSE 任务执行失败 task_id=%s",
                    task_id,
                )
                if not terminal_event_sent:
                    await queue.put(
                        AgentEvent(
                            type="error",
                            task_id=task_id,
                            content="任务执行失败",
                            data={"code": 500},
                        )
                    )
            finally:
                await queue.put(None)

        background_task = asyncio.create_task(run_task())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=15,
                    )
                except TimeoutError:
                    yield format_sse_event(
                        AgentEvent(
                            type="heartbeat",
                            task_id=task_id,
                        )
                    )
                    continue

                if event is None:
                    break

                yield format_sse_event(event)

            yield "event: done\ndata: [DONE]\n\n"
        finally:
            if not background_task.done():
                background_task.cancel()
                with suppress(asyncio.CancelledError):
                    await background_task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/match")
async def match_jobfit_agent(
    request: JobFitAgentRequest,
    current_user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(
        make_rate_limit_dependency("agent_match")
    ),
) -> dict:
    context = ToolContext(current_user=current_user)

    result = await run_jobfit_agent(
        job_description=request.job_description,
        resume_text=request.resume_text,
        context=context,
    )

    await record_daily_token_usage(
        get_redis_client(),
        user_id=current_user.id,
        total_tokens=result.usage.total_tokens,
    )
    return success_response(data=result)
