# 提供请求上下文、日志脱敏和任务指标模型。

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
_TASK_ID: ContextVar[int | None] = ContextVar("task_id", default=None)

_API_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_BEARER_PATTERN = re.compile(
    r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|password|secret|token)\s*[:=]\s*([^\s,;]+)"
)


class TaskMetrics(BaseModel):
    """一次 Agent 任务的可观测性汇总。"""

    request_id: str | None = None
    total_ms: int = Field(default=0, ge=0)
    model_ms: int = Field(default=0, ge=0)
    tool_ms: int = Field(default=0, ge=0)
    index_ms: int = Field(default=0, ge=0)
    retrieval_ms: int = Field(default=0, ge=0)
    rerank_ms: int = Field(default=0, ge=0)
    node_ms: int = Field(default=0, ge=0)
    steps: int = Field(default=0, ge=0)
    usage: dict[str, int] = Field(default_factory=dict)
    node_metrics: list[dict[str, Any]] = Field(default_factory=list)
    error_code: str | None = None
    estimated_cost: float = Field(default=0.0, ge=0)
    currency: str = "USD"
    usage_call_count: int = Field(default=0, ge=0)
    usage_by_model: dict[str, dict[str, int | float]] = Field(
        default_factory=dict
    )


def new_request_id() -> str:
    return uuid4().hex


def set_request_id(request_id: str | None) -> Token:
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token) -> None:
    _REQUEST_ID.reset(token)


def get_request_id() -> str | None:
    return _REQUEST_ID.get()


def set_task_id(task_id: int | None) -> Token:
    return _TASK_ID.set(task_id)


def reset_task_id(token: Token) -> None:
    _TASK_ID.reset(token)


def get_task_id() -> int | None:
    return _TASK_ID.get()


def redact_text(value: object) -> str:
    """移除日志文本中的常见凭证和敏感字段值。"""

    text = str(value)
    text = _API_KEY_PATTERN.sub("sk-***", text)
    text = _BEARER_PATTERN.sub("Bearer ***", text)
    text = _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}=***",
        text,
    )
    return text


def redact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    """递归脱敏字典中的凭证字段。"""

    sensitive_keys = {
        "api_key",
        "apikey",
        "authorization",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
    }
    result: dict[str, Any] = {}
    for key, item in value.items():
        normalized = str(key).strip().lower()
        if normalized in sensitive_keys:
            result[key] = "***"
        elif isinstance(item, dict):
            result[key] = redact_mapping(item)
        elif isinstance(item, list):
            result[key] = [
                redact_mapping(child)
                if isinstance(child, dict)
                else redact_text(child)
                for child in item
            ]
        else:
            result[key] = redact_text(item)
    return result


def build_task_metrics(
    *,
    request_id: str | None,
    total_ms: int,
    model_ms: int = 0,
    tool_ms: int = 0,
    index_ms: int = 0,
    retrieval_ms: int = 0,
    rerank_ms: int = 0,
    steps: int = 0,
    usage: dict[str, int] | None = None,
    node_metrics: list[dict[str, Any]] | None = None,
    error_code: str | None = None,
    estimated_cost: float = 0.0,
    currency: str = "USD",
    usage_call_count: int = 0,
    usage_by_model: dict[str, dict[str, int | float]] | None = None,
) -> TaskMetrics:
    normalized_nodes = node_metrics or []
    node_ms = sum(
        int(item.get("duration_ms", 0))
        for item in normalized_nodes
    )
    return TaskMetrics(
        request_id=request_id,
        total_ms=max(total_ms, 0),
        model_ms=max(model_ms, 0),
        tool_ms=max(tool_ms, 0),
        index_ms=max(index_ms, 0),
        retrieval_ms=max(retrieval_ms, 0),
        rerank_ms=max(rerank_ms, 0),
        node_ms=max(node_ms, 0),
        steps=max(steps, 0),
        usage=usage or {},
        node_metrics=normalized_nodes,
        error_code=error_code,
        estimated_cost=max(estimated_cost, 0.0),
        currency=currency,
        usage_call_count=max(usage_call_count, 0),
        usage_by_model=usage_by_model or {},
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "TaskMetrics",
    "build_task_metrics",
    "get_request_id",
    "get_task_id",
    "new_request_id",
    "redact_mapping",
    "redact_text",
    "reset_request_id",
    "reset_task_id",
    "set_request_id",
    "set_task_id",
    "utc_now_iso",
]
