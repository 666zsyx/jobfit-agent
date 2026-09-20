from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    AppError,
    app_error_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.routers.health import router as health_router
from app.routers.users import router as users_router
from app.routers.chat import router as chat_router
from app.routers.jobs import router as jobs_router

app = FastAPI(title="JobFit Agent")

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(health_router)
app.include_router(users_router)
app.include_router(chat_router)
app.include_router(jobs_router)