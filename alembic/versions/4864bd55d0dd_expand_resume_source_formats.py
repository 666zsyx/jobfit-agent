"""expand resume source formats

Revision ID: 4864bd55d0dd
Revises: 59152edc1d2e
Create Date: 2026-10-03 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = '4864bd55d0dd'
down_revision: Union[str, Sequence[str], None] = '59152edc1d2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_SOURCE_TYPE_CHECK = "source_type IN ('text', 'pdf')"
NEW_SOURCE_TYPE_CHECK = (
    "source_type IN ('text', 'pdf', 'docx', 'txt')"
)


def upgrade() -> None:
    """Upgrade schema."""

    op.drop_constraint(
        'resume_versions_source_type_check',
        'resume_versions',
        schema='jobfit',
        type_='check',
    )
    op.create_check_constraint(
        'resume_versions_source_type_check',
        'resume_versions',
        NEW_SOURCE_TYPE_CHECK,
        schema='jobfit',
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        'resume_versions_source_type_check',
        'resume_versions',
        schema='jobfit',
        type_='check',
    )
    op.create_check_constraint(
        'resume_versions_source_type_check',
        'resume_versions',
        OLD_SOURCE_TYPE_CHECK,
        schema='jobfit',
    )
