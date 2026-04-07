"""add turn generation traces

Revision ID: 20260407_000007
Revises: 20260407_000006
Create Date: 2026-04-07 22:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_000007"
down_revision = "20260407_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("session_turns", sa.Column("evaluation_trace", sa.JSON(), nullable=True))
    op.add_column("session_turns", sa.Column("teaching_trace", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("session_turns", "teaching_trace")
    op.drop_column("session_turns", "evaluation_trace")
