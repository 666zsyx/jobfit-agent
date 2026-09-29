# 映射 PostgreSQL 中的 jobfit.tool_call_records 表。

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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ToolCallRecord(Base):
    """一次 Agent 工具调用的审计记录。"""

    __tablename__ = "tool_call_records"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "tool_call_id",
            name="tool_call_records_task_id_tool_call_id_key",
        ),
        CheckConstraint(
            "step_no > 0",
            name="tool_call_records_step_no_check",
        ),
        CheckConstraint(
            "status IN ("
            "'started', 'success', 'validation_error', "
            "'timeout', 'error', 'unknown_tool'"
            ")",
            name="tool_call_records_status_check",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="tool_call_records_duration_ms_check",
        ),
        Index(
            "idx_tool_call_records_task_step",
            "task_id",
            "step_no",
        ),
        {"schema": "jobfit"},
    )

    tool_call_record_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "jobfit.analysis_tasks.task_id",
            name="tool_call_records_task_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_call_id: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    argument_keys: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    task: Mapped["AnalysisTask"] = relationship(
        back_populates="tool_call_records",
    )



