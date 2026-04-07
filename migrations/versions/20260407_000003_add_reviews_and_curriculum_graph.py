"""add reviews and curriculum graph

Revision ID: 20260407_000003
Revises: 20260407_000002
Create Date: 2026-04-07 15:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_000003"
down_revision = "20260407_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("learner_id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_review_items_due_at"), "review_items", ["due_at"], unique=False)
    op.create_index(op.f("ix_review_items_learner_id"), "review_items", ["learner_id"], unique=False)
    op.create_index(op.f("ix_review_items_status"), "review_items", ["status"], unique=False)
    op.create_index(op.f("ix_review_items_topic"), "review_items", ["topic"], unique=False)

    op.create_table(
        "concepts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_concepts_slug"), "concepts", ["slug"], unique=True)
    op.create_index(op.f("ix_concepts_subject"), "concepts", ["subject"], unique=False)

    op.create_table(
        "concept_prerequisites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.Column("prerequisite_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"]),
        sa.ForeignKeyConstraint(["prerequisite_id"], ["concepts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("concept_id", "prerequisite_id", name="uq_concept_prerequisite"),
    )
    op.create_index(
        op.f("ix_concept_prerequisites_concept_id"),
        "concept_prerequisites",
        ["concept_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_concept_prerequisites_prerequisite_id"),
        "concept_prerequisites",
        ["prerequisite_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_concept_prerequisites_prerequisite_id"), table_name="concept_prerequisites")
    op.drop_index(op.f("ix_concept_prerequisites_concept_id"), table_name="concept_prerequisites")
    op.drop_table("concept_prerequisites")
    op.drop_index(op.f("ix_concepts_subject"), table_name="concepts")
    op.drop_index(op.f("ix_concepts_slug"), table_name="concepts")
    op.drop_table("concepts")
    op.drop_index(op.f("ix_review_items_topic"), table_name="review_items")
    op.drop_index(op.f("ix_review_items_status"), table_name="review_items")
    op.drop_index(op.f("ix_review_items_learner_id"), table_name="review_items")
    op.drop_index(op.f("ix_review_items_due_at"), table_name="review_items")
    op.drop_table("review_items")
