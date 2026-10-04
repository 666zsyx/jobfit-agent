# 定义项目异常体系，并把异常转换为统一 HTTP 响应。

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


# 项目业务异常基类，统一携带消息和 HTTP 状态码。
class AppError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
    ):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# 表示上游 LLM 认证、限流、超时或连接失败。
class LLMServiceError(AppError):
    def __init__(
        self,
        message: str,
        status_code: int = 503,
    ):
        super().__init__(message=message, status_code=status_code)


# 表示模型调用成功，但结构化输出最终校验失败。
class StructuredOutputError(AppError):
    def __init__(
        self,
        message: str = "模型结构化输出校验失败",
        status_code: int = 502,
    ):
        super().__init__(message=message, status_code=status_code)


# 表示外部输入包含高风险 Prompt Injection 特征。
class UnsafeInputError(AppError):
    def __init__(
        self,
        message: str = "输入包含不安全指令",
        status_code: int = 400,
    ):
        super().__init__(message=message, status_code=status_code)


# 表示任务当前状态不允许执行请求的操作。
class ResumeFileError(AppError):
    def __init__(
        self,
        message: str,
        error_code: str,
        status_code: int = 422,
    ):
        self.error_code = error_code
        super().__init__(message=message, status_code=status_code)


class RateLimitExceededError(AppError):
    def __init__(
        self,
        message: str = "请求过于频繁或配额不足",
        retry_after_seconds: int = 60,
        limit_type: str = "rate_limit",
        status_code: int = 429,
    ):
        self.retry_after_seconds = max(retry_after_seconds, 1)
        self.limit_type = limit_type
        super().__init__(message=message, status_code=status_code)


class TaskStateConflictError(AppError):
    def __init__(
        self,
        message: str = "任务状态不允许执行该操作",
        status_code: int = 409,
    ):
        super().__init__(message=message, status_code=status_code)


# 把项目业务异常转换为统一错误响应。
async def app_error_handler(request: Request, exc: AppError):
    headers = {}
    if isinstance(exc, RateLimitExceededError):
        headers["Retry-After"] = str(exc.retry_after_seconds)

    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content={
            "code": exc.status_code,
            "message": exc.message,
            "data": (
                {"limit_type": exc.limit_type}
                if isinstance(exc, RateLimitExceededError)
                else {"error_code": exc.error_code}
                if isinstance(exc, ResumeFileError)
                else None
            ),
        },
    )


# 把 FastAPI/Starlette HTTP 异常转换为统一错误响应。
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "code": exc.status_code,
            "message": str(exc.detail),
            "data": None,
        },
    )


# 把请求参数校验错误转换为统一的 422 响应。
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "message": "请求参数校验失败",
            "data": jsonable_encoder(
                [
                    {
                        key: value
                        for key, value in error.items()
                        if key not in {"input", "url"}
                    }
                    for error in exc.errors()
                ]
            ),
        },
    )
