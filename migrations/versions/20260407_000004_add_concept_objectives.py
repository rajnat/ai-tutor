"""add concept objectives

Revision ID: 20260407_000004
Revises: 20260407_000003
Create Date: 2026-04-07 16:05:00
"""

from __future__ import annotations

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260407_000004"
down_revision = "20260407_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concept_objectives",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("mastery_threshold", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("concept_id", "slug", name="uq_concept_objective_slug"),
    )
    op.create_index(op.f("ix_concept_objectives_concept_id"), "concept_objectives", ["concept_id"], unique=False)

    op.create_table(
        "learner_objective_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("learner_id", sa.String(length=36), nullable=False),
        sa.Column("objective_id", sa.String(length=36), nullable=False),
        sa.Column("mastery", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"]),
        sa.ForeignKeyConstraint(["objective_id"], ["concept_objectives.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("learner_id", "objective_id", name="uq_learner_objective_states"),
    )
    op.create_index(
        op.f("ix_learner_objective_states_learner_id"),
        "learner_objective_states",
        ["learner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_learner_objective_states_objective_id"),
        "learner_objective_states",
        ["objective_id"],
        unique=False,
    )

    bind = op.get_bind()
    concepts = bind.execute(sa.text("SELECT id, slug, description FROM concepts")).mappings()
    defaults = [
        ("intuition", "Conceptual intuition"),
        ("notation", "Notation and vocabulary"),
        ("application", "Basic application"),
        ("transfer", "Transfer and explanation"),
    ]
    for concept in concepts:
        for suffix, title in defaults:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO concept_objectives
                    (id, concept_id, slug, title, description, mastery_threshold)
                    VALUES (:id, :concept_id, :slug, :title, :description, :mastery_threshold)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "concept_id": concept["id"],
                    "slug": f"{concept['slug']}:{suffix}",
                    "title": title,
                    "description": f"{title} for {concept['slug']}. {concept['description']}",
                    "mastery_threshold": 0.7,
                },
            )


def downgrade() -> None:
    op.drop_index(op.f("ix_learner_objective_states_objective_id"), table_name="learner_objective_states")
    op.drop_index(op.f("ix_learner_objective_states_learner_id"), table_name="learner_objective_states")
    op.drop_table("learner_objective_states")
    op.drop_index(op.f("ix_concept_objectives_concept_id"), table_name="concept_objectives")
    op.drop_table("concept_objectives")
