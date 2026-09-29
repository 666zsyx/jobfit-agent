# 对会话历史做有界压缩，避免把全部消息送入模型。

from collections.abc import Sequence

from app.db.models import Message


DEFAULT_CONTEXT_MAX_CHARS = 8_000
DEFAULT_MESSAGE_MAX_CHARS = 2_000


def build_compressed_conversation_context(
    messages: Sequence[Message],
    *,
    max_chars: int = DEFAULT_CONTEXT_MAX_CHARS,
    message_max_chars: int = DEFAULT_MESSAGE_MAX_CHARS,
) -> str:
    """保留最近消息，超出预算时从较早消息开始省略。"""

    if max_chars <= 0:
        raise ValueError("max_chars 必须大于 0")

    if message_max_chars <= 0:
        raise ValueError("message_max_chars 必须大于 0")

    candidate_messages = [
        message
        for message in messages
        if message.content and message.content.strip()
    ]
    selected: list[str] = []
    used_chars = 0

    for message in reversed(candidate_messages):
        content = message.content.strip()
        if len(content) > message_max_chars:
            content = content[:message_max_chars] + "...[内容已截断]"

        rendered = f"{message.role}: {content}"
        separator_chars = 1 if selected else 0
        required_chars = len(rendered) + separator_chars

        if selected and used_chars + required_chars > max_chars:
            break

        selected.append(rendered)
        used_chars += required_chars

    if not selected:
        return ""

    selected.reverse()
    omitted = len(candidate_messages) > len(selected)
    prefix = "[较早会话已省略]\n" if omitted else ""
    return prefix + "\n".join(selected)


__all__ = [
    "DEFAULT_CONTEXT_MAX_CHARS",
    "DEFAULT_MESSAGE_MAX_CHARS",
    "build_compressed_conversation_context",
]
