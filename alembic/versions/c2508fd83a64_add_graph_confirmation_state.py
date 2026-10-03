"""add graph confirmation state

Revision ID: c2508fd83a64
Revises: 7bbfe67997b0
Create Date: 2026-10-03 18:16:18.484845

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2508fd83a64'
down_revision: Union[str, Sequence[str], None] = '7bbfe67997b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_STATUS_CHECK = (
    "status IN ("
    "'pending', 'running', 'interrupted', "
    "'completed', 'failed', 'cancelled'"
    ")"
)

NEW_STATUS_CHECK = (
    "status IN ("
    "'pending', 'running', 'waiting_confirmation', 'interrupted', "
    "'completed', 'failed', 'cancelled'"
    ")"
)


def upgrade() -> None:
    """Upgrade schema."""

    op.drop_constraint(
        'analysis_tasks_status_check',
        'analysis_tasks',
        schema='jobfit',
        type_='check',
    )
    op.add_column(
        'analysis_tasks',
        sa.Column('current_node', sa.Text(), nullable=True),
        schema='jobfit',
    )
    op.create_check_constraint(
        'analysis_tasks_status_check',
        'analysis_tasks',
        NEW_STATUS_CHECK,
        schema='jobfit',
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        'analysis_tasks_status_check',
        'analysis_tasks',
        schema='jobfit',
        type_='check',
    )
    op.drop_column(
        'analysis_tasks',
        'current_node',
        schema='jobfit',
    )
    op.create_check_constraint(
        'analysis_tasks_status_check',
        'analysis_tasks',
        OLD_STATUS_CHECK,
        schema='jobfit',
    )
