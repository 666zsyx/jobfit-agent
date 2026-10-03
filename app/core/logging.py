# 配置结构化日志、request_id 注入和敏感信息脱敏。

from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone

from app.core.observability import (
    get_request_id,
    get_task_id,
    redact_text,
)


class ContextFilter(logging.Filter):
    """把 request_id 和 task_id 注入日志记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        record.task_id = get_task_id() or "-"
        return True


class SensitiveDataFilter(logging.Filter):
    """在日志格式化前移除常见凭证。"""

    def filter(self, record: logging.LogRecord) -> bool:
        message = redact_text(record.getMessage())
        if record.exc_info:
            exception_text = "".join(
                traceback.format_exception(*record.exc_info)
            )
            message = f"{message}\n{redact_text(exception_text)}"
            record.exc_info = None
            record.exc_text = None
        record.msg = message
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """输出包含上下文的 JSON 日志。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "request_id": getattr(record, "request_id", "-"),
            "task_id": getattr(record, "task_id", "-"),
        }
        if record.exc_text:
            payload["exception"] = redact_text(record.exc_text)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """输出包含 request_id 的文本日志。"""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        return (
            f"{base} request_id={getattr(record, 'request_id', '-')} "
            f"task_id={getattr(record, 'task_id', '-')}"
        )


def configure_logging() -> None:
    """配置根日志器，重复调用不会叠加 handler。"""

    root = logging.getLogger()
    if getattr(root, "_jobfit_configured", False):
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_format = os.getenv("LOG_FORMAT", "text").strip().lower()

    handler = logging.StreamHandler()
    handler.addFilter(ContextFilter())
    handler.addFilter(SensitiveDataFilter())

    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            TextFormatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s"
            )
        )

    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root._jobfit_configured = True


__all__ = [
    "ContextFilter",
    "JsonFormatter",
    "SensitiveDataFilter",
    "TextFormatter",
    "configure_logging",
]
