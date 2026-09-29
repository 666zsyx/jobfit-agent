# 映射 PostgreSQL 中的 jobfit.conversations 表。

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Conversation(Base):
    """一段 JobFit Agent 会话。"""

    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="conversations_status_check",
        ),
        Index(
            "idx_conversations_user_updated_at",
            "user_id",
            "updated_at",
        ),
        {"schema": "jobfit"},
    )

    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "jobfit.users.user_id",
            name="conversations_user_id_fkey",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="active",
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.sequence_no",
    )
    analysis_tasks: Mapped[list["AnalysisTask"]] = relationship(
        back_populates="conversation",
    )



