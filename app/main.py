# 创建 FastAPI 应用并注册路由与全局异常处理。

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.cache.client import dispose_redis
from app.core.event_loop import configure_event_loop_policy
from app.core.exceptions import (
    AppError,
    app_error_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.db.session import dispose_engine
from app.routers.agent import router as agent_router
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.routers.jobs import router as jobs_router
from app.routers.users import router as users_router


configure_event_loop_policy()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await dispose_redis()
        await dispose_engine()


app = FastAPI(title="JobFit Agent", lifespan=lifespan)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(health_router)
app.include_router(users_router)
app.include_router(chat_router)
app.include_router(jobs_router)
app.include_router(agent_router)
