# 映射 PostgreSQL 中的 jobfit.users 表。

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    """JobFit 用户模型。"""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="users_username_key"),
        UniqueConstraint("email", name="users_email_key"),
        CheckConstraint(
            "role IN ('user', 'admin')",
            name="users_role_check",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="users_status_check",
        ),
        {"schema": "jobfit"},
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    username: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="user",
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="active",
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

    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="user",
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="user",
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user",
    )
    analysis_tasks: Mapped[list["AnalysisTask"]] = relationship(
        back_populates="user",
    )
