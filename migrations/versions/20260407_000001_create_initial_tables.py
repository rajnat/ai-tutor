"""create initial tables

Revision ID: 20260407_000001
Revises:
Create Date: 2026-04-07 14:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learners",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("misconceptions", sa.JSON(), nullable=False),
        sa.Column("learning_style", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("learner_id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("turns", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sessions_learner_id"), "sessions", ["learner_id"], unique=False)
    op.create_index(op.f("ix_sessions_topic"), "sessions", ["topic"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sessions_topic"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_learner_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("learners")
