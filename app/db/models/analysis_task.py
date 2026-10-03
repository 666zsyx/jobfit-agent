# 映射 PostgreSQL 中的 jobfit.analysis_tasks 表。

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AnalysisTask(Base):
    """一次可追踪、可恢复的岗位分析任务。"""

    __tablename__ = "analysis_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'pending', 'running', 'waiting_confirmation', 'interrupted', "
            "'completed', 'failed', 'cancelled'"
            ")",
            name="analysis_tasks_status_check",
        ),
        CheckConstraint(
            "current_step >= 0",
            name="analysis_tasks_current_step_check",
        ),
        CheckConstraint(
            "attempt >= 0",
            name="analysis_tasks_attempt_check",
        ),
        CheckConstraint(
            "max_steps > 0",
            name="analysis_tasks_max_steps_check",
        ),
        CheckConstraint(
            "current_step <= max_steps",
            name="analysis_tasks_check",
        ),
        Index(
            "idx_analysis_tasks_user_created_at",
            "user_id",
            "created_at",
        ),
        Index(
            "idx_analysis_tasks_status_created_at",
            "status",
            "created_at",
        ),
        Index(
            "idx_analysis_tasks_conversation_id",
            "conversation_id",
        ),
        Index(
            "idx_analysis_tasks_resume_version_id",
            "resume_version_id",
        ),
        Index(
            "idx_analysis_tasks_job_id",
            "job_id",
        ),
        {"schema": "jobfit"},
    )

    task_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "jobfit.users.user_id",
            name="analysis_tasks_user_id_fkey",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    conversation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "jobfit.conversations.conversation_id",
            name="analysis_tasks_conversation_id_fkey",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    resume_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "jobfit.resume_versions.resume_version_id",
            name="analysis_tasks_resume_version_id_fkey",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "jobfit.jobs.job_id",
            name="analysis_tasks_job_id_fkey",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="pending",
    )
    current_step: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    max_steps: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="8",
    )
    current_node: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    last_request_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    metrics_json: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    error_message_safe: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
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

    user: Mapped["User"] = relationship(back_populates="analysis_tasks")
    conversation: Mapped["Conversation | None"] = relationship(
        back_populates="analysis_tasks",
    )
    resume_version: Mapped["ResumeVersion"] = relationship(
        back_populates="analysis_tasks",
    )
    job: Mapped["Job"] = relationship(back_populates="analysis_tasks")
    reports: Mapped[list["Report"]] = relationship(
        back_populates="task",
        order_by="Report.version_no",
    )
    tool_call_records: Mapped[list["ToolCallRecord"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ToolCallRecord.step_no",
    )
