# 验证 request_id、日志脱敏和任务指标。

import logging

from app.core.observability import (
    build_task_metrics,
    redact_mapping,
    redact_text,
    reset_request_id,
    set_request_id,
)
from app.core.logging import JsonFormatter, SensitiveDataFilter


def test_redact_text_removes_common_secrets() -> None:
    text = (
        "Authorization: Bearer demo-token "
        "api_key=sk-1234567890abcdef password=secret"
    )
    redacted = redact_text(text)

    assert "demo-token" not in redacted
    assert "sk-1234567890abcdef" not in redacted
    assert "secret" not in redacted
    assert "Bearer ***" in redacted
    assert "api_key=***" in redacted
    assert "password=***" in redacted


def test_redact_mapping_recurses() -> None:
    value = {
        "password": "secret",
        "outer": {"token": "abc"},
        "items": [{"api_key": "sk-abcdefgh"}],
    }
    redacted = redact_mapping(value)

    assert redacted["password"] == "***"
    assert redacted["outer"]["token"] == "***"
    assert redacted["items"][0]["api_key"] == "***"


def test_json_formatter_contains_request_id() -> None:
    token = set_request_id("req-12345678")
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.request_id = "req-12345678"
        record.task_id = 10
        output = JsonFormatter().format(record)
    finally:
        reset_request_id(token)

    assert '"request_id": "req-12345678"' in output
    assert '"task_id": 10' in output


def test_sensitive_filter_redacts_log_message() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token=secret-value",
        args=(),
        exc_info=None,
    )
    SensitiveDataFilter().filter(record)
    assert "secret-value" not in record.getMessage()
    assert "token=***" in record.getMessage()


def test_task_metrics_sum_node_durations() -> None:
    metrics = build_task_metrics(
        request_id="req-1",
        total_ms=100,
        model_ms=30,
        tool_ms=20,
        steps=2,
        usage={"total_tokens": 100},
        node_metrics=[
            {"node": "agent_decide", "duration_ms": 30},
            {"node": "execute_tools", "duration_ms": 20},
        ],
    )

    assert metrics.node_ms == 50
    assert metrics.model_ms == 30
    assert metrics.tool_ms == 20


def test_request_id_header_is_generated(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_request_id_header_is_preserved(client) -> None:
    response = client.get(
        "/health",
        headers={"X-Request-ID": "client-request-1234"},
    )

    assert response.headers["X-Request-ID"] == "client-request-1234"
