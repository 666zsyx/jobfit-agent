"""add task observability fields

Revision ID: 59152edc1d2e
Revises: c2508fd83a64
Create Date: 2026-10-03 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '59152edc1d2e'
down_revision: Union[str, Sequence[str], None] = 'c2508fd83a64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        'analysis_tasks',
        sa.Column('last_request_id', sa.Text(), nullable=True),
        schema='jobfit',
    )
    op.add_column(
        'analysis_tasks',
        sa.Column(
            'metrics_json',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        schema='jobfit',
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column(
        'analysis_tasks',
        'metrics_json',
        schema='jobfit',
    )
    op.drop_column(
        'analysis_tasks',
        'last_request_id',
        schema='jobfit',
    )
