# 映射 PostgreSQL 中的 jobfit.messages 表。

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Message(Base):
    """会话中的一条消息。"""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "sequence_no",
            name="messages_conversation_id_sequence_no_key",
        ),
        CheckConstraint(
            "sequence_no > 0",
            name="messages_sequence_no_check",
        ),
        CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="messages_role_check",
        ),
        {"schema": "jobfit"},
    )

    message_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "jobfit.conversations.conversation_id",
            name="messages_conversation_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages",
    )

