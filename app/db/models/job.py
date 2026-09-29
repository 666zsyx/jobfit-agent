# 映射 PostgreSQL 中的 jobfit.jobs 表。

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Job(Base):
    """用户录入并结构化的岗位 JD。"""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="jobs_status_check",
        ),
        Index(
            "idx_jobs_user_created_at",
            "user_id",
            "created_at",
        ),
        {"schema": "jobfit"},
    )

    job_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "jobfit.users.user_id",
            name="jobs_user_id_fkey",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_requirements: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
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

    user: Mapped["User"] = relationship(back_populates="jobs")
    analysis_tasks: Mapped[list["AnalysisTask"]] = relationship(
        back_populates="job",
    )



