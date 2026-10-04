# 创建 FastAPI 应用并注册路由与全局异常处理。

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.cache.client import dispose_redis
from app.core.event_loop import configure_event_loop_policy
from app.core.logging import configure_logging
from app.core.exceptions import (
    AppError,
    app_error_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.db.session import async_session_factory, dispose_engine
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers.agent import router as agent_router
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.routers.jobs import router as jobs_router
from app.routers.pages import STATIC_DIRECTORY, router as pages_router
from app.routers.resumes import router as resumes_router
from app.routers.users import router as users_router
from app.services.analysis_results import recover_stale_running_tasks


configure_event_loop_policy()
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        try:
            async with async_session_factory() as session:
                async with session.begin():
                    recovered = await recover_stale_running_tasks(
                        session
                    )
            if recovered:
                logger.warning(
                    "启动时恢复遗留 running 任务数量=%s",
                    recovered,
                )
        except Exception:
            logger.warning("启动时清理遗留任务失败", exc_info=True)

        yield
    finally:
        await dispose_redis()
        await dispose_engine()


app = FastAPI(title="JobFit Agent", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIRECTORY),
    name="static",
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(pages_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(chat_router)
app.include_router(jobs_router)
app.include_router(resumes_router)
app.include_router(agent_router)
