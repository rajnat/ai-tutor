"""add turn objective id

Revision ID: 20260407_000005
Revises: 20260407_000004
Create Date: 2026-04-07 16:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_000005"
down_revision = "20260407_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("session_turns") as batch_op:
        batch_op.add_column(sa.Column("objective_id", sa.String(length=36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("session_turns") as batch_op:
        batch_op.drop_column("objective_id")
