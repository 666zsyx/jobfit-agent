# 定义 Graph 节点的重试分类和重试策略。

from __future__ import annotations

from langgraph.types import RetryPolicy

from app.core.exceptions import LLMServiceError


RETRYABLE_LLM_STATUS_CODES = {502, 503, 504}


def is_retryable_graph_error(exc: Exception) -> bool:
    """只重试临时网络、超时和服务端错误。"""

    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True

    if isinstance(exc, LLMServiceError):
        return exc.status_code in RETRYABLE_LLM_STATUS_CODES

    return False


LLM_RETRY_POLICY = RetryPolicy(
    initial_interval=0.01,
    backoff_factor=2.0,
    max_interval=0.1,
    max_attempts=3,
    jitter=False,
    retry_on=is_retryable_graph_error,
)


__all__ = [
    "LLM_RETRY_POLICY",
    "is_retryable_graph_error",
]
