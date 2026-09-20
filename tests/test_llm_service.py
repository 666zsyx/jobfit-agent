import asyncio
from types import SimpleNamespace

from app.services import llm


def make_fake_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            ),
        ],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    )


def assert_chat_result(result, expected_answer: str) -> None:
    assert result.answer == expected_answer
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5
    assert result.usage.total_tokens == 15
    assert isinstance(result.latency_ms, int)


def test_chat_does_not_send_response_format(monkeypatch):
    calls = []
    messages = [{"role": "user", "content": "普通聊天"}]

    async def fake_create(**kwargs):
        calls.append(kwargs)
        return make_fake_response("普通回答")

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)

    result = asyncio.run(llm.chat(messages))

    assert calls == [
        {
            "model": llm.settings.llm_model,
            "messages": messages,
        }
    ]
    assert "response_format" not in calls[0]
    assert_chat_result(result, "普通回答")


def test_chat_json_sends_json_object_response_format(monkeypatch):
    calls = []
    messages = [{"role": "user", "content": "返回测试 JSON"}]

    async def fake_create(**kwargs):
        calls.append(kwargs)
        return make_fake_response('{"status":"ok"}')

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)

    result = asyncio.run(llm.chat_json(messages))

    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["messages"] == messages
    assert_chat_result(result, '{"status":"ok"}')
