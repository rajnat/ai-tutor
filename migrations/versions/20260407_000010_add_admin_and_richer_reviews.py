"""add admin role and richer reviews

Revision ID: 20260407_000010
Revises: 20260407_000009
Create Date: 2026-04-07 23:58:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_000010"
down_revision = "20260407_000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "review_items",
        sa.Column(
            "prompt",
            sa.Text(),
            nullable=False,
            server_default="Review this topic in your own words.",
        ),
    )
    op.add_column("review_items", sa.Column("objective_id", sa.String(length=36), nullable=True))
    op.add_column("review_items", sa.Column("objective_slug", sa.String(length=255), nullable=True))
    op.add_column("review_items", sa.Column("expected_answer", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("review_items", "expected_answer")
    op.drop_column("review_items", "objective_slug")
    op.drop_column("review_items", "objective_id")
    op.drop_column("review_items", "prompt")
    op.drop_column("accounts", "is_admin")
