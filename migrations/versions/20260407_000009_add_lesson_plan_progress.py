"""add lesson plan progress

Revision ID: 20260407_000009
Revises: 20260407_000008
Create Date: 2026-04-07 23:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_000009"
down_revision = "20260407_000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lesson_plans", sa.Column("current_step_index", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("lesson_plans", sa.Column("completed_step_ids", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("lesson_plans", "completed_step_ids")
    op.drop_column("lesson_plans", "current_step_index")
