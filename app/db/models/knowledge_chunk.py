# 映射 PostgreSQL 中的 jobfit.knowledge_chunks 表。

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class KnowledgeChunk(Base):
    """一条可持久化、可追溯的简历知识证据。"""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "resume_version_id",
            "chunker_version",
            "position",
            name=(
                "knowledge_chunks_resume_version_id_"
                "chunker_version_position_key"
            ),
        ),
        CheckConstraint(
            "position > 0",
            name="knowledge_chunks_position_check",
        ),
        CheckConstraint(
            (
                "section_type IN "
                "('summary', 'education', 'work_experience', "
                "'project_experience', 'skills', 'certificates', 'other')"
            ),
            name="knowledge_chunks_section_type_check",
        ),
        CheckConstraint(
            "start_offset IS NULL OR start_offset >= 0",
            name="knowledge_chunks_start_offset_check",
        ),
        CheckConstraint(
            "end_offset IS NULL OR end_offset >= 0",
            name="knowledge_chunks_end_offset_check",
        ),
        CheckConstraint(
            (
                "start_offset IS NULL OR end_offset IS NULL "
                "OR end_offset > start_offset"
            ),
            name="knowledge_chunks_offset_order_check",
        ),
        CheckConstraint(
            "index_status IN ('pending', 'indexed', 'failed', 'stale')",
            name="knowledge_chunks_index_status_check",
        ),
        CheckConstraint(
            (
                "embedding_dimension IS NULL "
                "OR embedding_dimension > 0"
            ),
            name="knowledge_chunks_embedding_dimension_check",
        ),
        Index(
            "idx_knowledge_chunks_user_resume_version",
            "user_id",
            "resume_version_id",
        ),
        Index(
            "idx_knowledge_chunks_resume_version_status",
            "resume_version_id",
            "index_status",
        ),
        Index(
            "idx_knowledge_chunks_user_content_hash",
            "user_id",
            "content_hash",
        ),
        {"schema": "jobfit"},
    )

    chunk_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "jobfit.users.user_id",
            name="knowledge_chunks_user_id_fkey",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    resume_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "jobfit.resume_versions.resume_version_id",
            name="knowledge_chunks_resume_version_id_fkey",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    section_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_offset: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    end_offset: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    chunker_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="v1",
    )
    index_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="pending",
    )
    embedding_model: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    embedding_dimension: Mapped[int | None] = mapped_column(
        Integer,
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

    resume_version: Mapped["ResumeVersion"] = relationship(
        back_populates="knowledge_chunks",
    )
