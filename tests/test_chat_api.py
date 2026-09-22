# 验证聊天接口的鉴权、请求校验和响应结构。

import json
from collections.abc import AsyncIterator

import pytest

from app.core.exceptions import LLMServiceError
from app.routers import chat as chat_router
from app.schemas.chat import ChatResult, LLMStreamEvent, TokenUsage


def parse_sse_events(body: str) -> list[dict]:
    events = []

    for line in body.splitlines():
        if not line.startswith("data: "):
            continue

        data = line.removeprefix("data: ")
        if data == "[DONE]":
            continue

        events.append(json.loads(data))

    return events


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_requires_auth(client):
    response = client.post(
        "/api/chat",
        json={
            "messages": [
                {"role": "user", "content": "你好"},
            ],
        },
    )

    assert response.status_code == 401
    assert response.json()["message"] == "未提供身份验证凭证"


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [{"role": "robot", "content": "你好"}],
        [{"role": "user", "content": ""}],
    ],
)
def test_chat_validates_request(client, auth_headers, messages):
    response = client.post(
        "/api/chat",
        headers=auth_headers,
        json={"messages": messages},
    )

    assert response.status_code == 422
    assert response.json()["message"] == "请求参数校验失败"


def test_chat_returns_answer_usage_and_latency(
    client,
    auth_headers,
    monkeypatch,
):
    async def fake_chat(messages: list[dict[str, str]]) -> ChatResult:
        assert messages == [{"role": "user", "content": "你好"}]

        return ChatResult(
            answer="你好，我是测试回答。",
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=7,
                total_tokens=17,
            ),
            latency_ms=123,
        )

    monkeypatch.setattr(chat_router, "llm_chat", fake_chat)

    response = client.post(
        "/api/chat",
        headers=auth_headers,
        json={
            "messages": [
                {"role": "user", "content": "你好"},
            ],
        },
    )

    assert response.status_code == 200

    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"] == {
        "answer": "你好，我是测试回答。",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 7,
            "total_tokens": 17,
        },
        "latency_ms": 123,
    }


def test_chat_maps_service_error_to_http_response(
    client,
    auth_headers,
    monkeypatch,
):
    async def failing_chat(messages: list[dict[str, str]]) -> ChatResult:
        raise LLMServiceError(
            message="LLM 请求超时，请稍后重试。",
            status_code=504,
        )

    monkeypatch.setattr(chat_router, "llm_chat", failing_chat)

    response = client.post(
        "/api/chat",
        headers=auth_headers,
        json={
            "messages": [
                {"role": "user", "content": "你好"},
            ],
        },
    )

    assert response.status_code == 504
    assert response.json() == {
        "code": 504,
        "message": "LLM 请求超时，请稍后重试。",
        "data": None,
    }


def test_stream_chat_returns_sse_content_usage_and_done(
    client,
    auth_headers,
    monkeypatch,
):
    async def fake_stream_chat(
        messages: list[dict[str, str]],
    ) -> AsyncIterator[LLMStreamEvent]:
        assert messages == [{"role": "user", "content": "你好"}]

        yield LLMStreamEvent(type="content", content="你")
        yield LLMStreamEvent(type="content", content="好")
        yield LLMStreamEvent(
            type="usage",
            usage=TokenUsage(
                prompt_tokens=8,
                completion_tokens=2,
                total_tokens=10,
            ),
            latency_ms=456,
        )

    monkeypatch.setattr(chat_router, "llm_stream_chat", fake_stream_chat)

    with client.stream(
        "POST",
        "/api/chat/stream",
        headers=auth_headers,
        json={
            "messages": [
                {"role": "user", "content": "你好"},
            ],
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.read().decode("utf-8")

    events = parse_sse_events(body)

    assert events == [
        {"type": "content", "content": "你"},
        {"type": "content", "content": "好"},
        {
            "type": "usage",
            "usage": {
                "prompt_tokens": 8,
                "completion_tokens": 2,
                "total_tokens": 10,
            },
            "latency_ms": 456,
        },
    ]
    assert body.endswith("data: [DONE]\n\n")


def test_stream_chat_returns_sse_error_and_done(
    client,
    auth_headers,
    monkeypatch,
):
    async def failing_stream_chat(
        messages: list[dict[str, str]],
    ) -> AsyncIterator[LLMStreamEvent]:
        raise LLMServiceError(
            message="LLM 服务暂时不可用。",
            status_code=503,
        )
        yield LLMStreamEvent(type="content", content="不会执行")

    monkeypatch.setattr(chat_router, "llm_stream_chat", failing_stream_chat)

    with client.stream(
        "POST",
        "/api/chat/stream",
        headers=auth_headers,
        json={
            "messages": [
                {"role": "user", "content": "你好"},
            ],
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    events = parse_sse_events(body)

    assert events == [
        {
            "type": "error",
            "message": "LLM 服务暂时不可用。",
        },
    ]
    assert body.endswith("data: [DONE]\n\n")
