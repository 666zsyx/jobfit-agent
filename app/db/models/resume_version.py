# 映射 PostgreSQL 中的 jobfit.resume_versions 表。

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


class ResumeVersion(Base):
    """一份简历的具体版本。"""

    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint(
            "resume_id",
            "version_no",
            name="resume_versions_resume_id_version_no_key",
        ),
        CheckConstraint(
            "version_no > 0",
            name="resume_versions_version_no_check",
        ),
        CheckConstraint(
            "source_type IN ('text', 'pdf')",
            name="resume_versions_source_type_check",
        ),
        {"schema": "jobfit"},
    )

    resume_version_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    resume_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "jobfit.resumes.resume_id",
            name="resume_versions_resume_id_fkey",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_sections: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="text",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    resume: Mapped["Resume"] = relationship(back_populates="versions")
    analysis_tasks: Mapped[list["AnalysisTask"]] = relationship(
        back_populates="resume_version",
    )

    knowledge_chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="resume_version",
        order_by="KnowledgeChunk.position",
    )
