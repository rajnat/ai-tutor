"""add lesson plans

Revision ID: 20260407_000008
Revises: 20260407_000007
Create Date: 2026-04-07 23:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_000008"
down_revision = "20260407_000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lesson_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("learner_id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("trace", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lesson_plans_learner_id"), "lesson_plans", ["learner_id"], unique=False)
    op.create_index(op.f("ix_lesson_plans_status"), "lesson_plans", ["status"], unique=False)
    op.create_index(op.f("ix_lesson_plans_topic"), "lesson_plans", ["topic"], unique=False)

    op.create_table(
        "lesson_plan_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("lesson_plan_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("objective_id", sa.String(length=36), nullable=True),
        sa.Column("objective_slug", sa.String(length=255), nullable=True),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("step_type", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["lesson_plan_id"], ["lesson_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_plan_id", "position", name="uq_lesson_plan_step_position"),
    )
    op.create_index(op.f("ix_lesson_plan_steps_lesson_plan_id"), "lesson_plan_steps", ["lesson_plan_id"], unique=False)
    op.create_index(op.f("ix_lesson_plan_steps_position"), "lesson_plan_steps", ["position"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lesson_plan_steps_position"), table_name="lesson_plan_steps")
    op.drop_index(op.f("ix_lesson_plan_steps_lesson_plan_id"), table_name="lesson_plan_steps")
    op.drop_table("lesson_plan_steps")
    op.drop_index(op.f("ix_lesson_plans_topic"), table_name="lesson_plans")
    op.drop_index(op.f("ix_lesson_plans_status"), table_name="lesson_plans")
    op.drop_index(op.f("ix_lesson_plans_learner_id"), table_name="lesson_plans")
    op.drop_table("lesson_plans")
