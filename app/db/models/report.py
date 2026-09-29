# 映射 PostgreSQL 中的 jobfit.reports 表。

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
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Report(Base):
    """岗位分析任务生成的报告版本。"""

    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "version_no",
            name="reports_task_id_version_no_key",
        ),
        CheckConstraint(
            "version_no > 0",
            name="reports_version_no_check",
        ),
        Index(
            "idx_reports_one_current_per_task",
            "task_id",
            unique=True,
            postgresql_where=text(
                "is_current = TRUE AND deleted_at IS NULL"
            ),
        ),
        {"schema": "jobfit"},
    )

    report_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "jobfit.analysis_tasks.task_id",
            name="reports_task_id_fkey",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=false(),
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
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

    task: Mapped["AnalysisTask"] = relationship(
        back_populates="reports",
    )



