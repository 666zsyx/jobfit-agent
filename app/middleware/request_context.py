# 给每个 HTTP 请求设置 request_id，并在响应头返回。

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.datastructures import MutableHeaders

from app.core.observability import (
    new_request_id,
    reset_request_id,
    set_request_id,
)


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestContextMiddleware:
    """纯 ASGI 中间件，兼容 SSE 流式响应。"""

    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
    ) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw_request_id = headers.get(b"x-request-id", b"").decode(
            "latin-1",
            errors="ignore",
        )
        request_id = (
            raw_request_id
            if REQUEST_ID_PATTERN.fullmatch(raw_request_id)
            else new_request_id()
        )

        token = set_request_id(request_id)

        async def send_with_request_id(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            reset_request_id(token)


__all__ = ["RequestContextMiddleware", "REQUEST_ID_PATTERN"]
