"""add courses and section content

Revision ID: 20260408_000011
Revises: 20260407_000010
Create Date: 2026-04-08 09:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_000011"
down_revision = "20260407_000010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("learner_id", sa.String(length=36), sa.ForeignKey("learners.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("study_prompt", sa.Text(), nullable=False),
        sa.Column("topic_slug", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_section_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_courses_learner_id", "courses", ["learner_id"])
    op.create_index("ix_courses_topic_slug", "courses", ["topic_slug"])
    op.create_index("ix_courses_subject", "courses", ["subject"])
    op.create_index("ix_courses_status", "courses", ["status"])

    op.create_table(
        "course_sections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("course_id", sa.String(length=36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("objective_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("course_id", "position", name="uq_course_section_position"),
    )
    op.create_index("ix_course_sections_course_id", "course_sections", ["course_id"])
    op.create_index("ix_course_sections_position", "course_sections", ["position"])
    op.create_index("ix_course_sections_slug", "course_sections", ["slug"])
    op.create_index("ix_course_sections_status", "course_sections", ["status"])

    op.create_table(
        "course_section_contents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("course_id", sa.String(length=36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("section_id", sa.String(length=36), sa.ForeignKey("course_sections.id"), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_course_section_contents_course_id", "course_section_contents", ["course_id"])
    op.create_index("ix_course_section_contents_section_id", "course_section_contents", ["section_id"])

    op.create_table(
        "checkpoint_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("learner_id", sa.String(length=36), sa.ForeignKey("learners.id"), nullable=False),
        sa.Column("course_id", sa.String(length=36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=36), nullable=False),
        sa.Column("selected_option_id", sa.String(length=64), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_checkpoint_attempts_learner_id", "checkpoint_attempts", ["learner_id"])
    op.create_index("ix_checkpoint_attempts_course_id", "checkpoint_attempts", ["course_id"])
    op.create_index("ix_checkpoint_attempts_session_id", "checkpoint_attempts", ["session_id"])
    op.create_index("ix_checkpoint_attempts_checkpoint_id", "checkpoint_attempts", ["checkpoint_id"])


def downgrade() -> None:
    op.drop_index("ix_checkpoint_attempts_checkpoint_id", table_name="checkpoint_attempts")
    op.drop_index("ix_checkpoint_attempts_session_id", table_name="checkpoint_attempts")
    op.drop_index("ix_checkpoint_attempts_course_id", table_name="checkpoint_attempts")
    op.drop_index("ix_checkpoint_attempts_learner_id", table_name="checkpoint_attempts")
    op.drop_table("checkpoint_attempts")

    op.drop_index("ix_course_section_contents_section_id", table_name="course_section_contents")
    op.drop_index("ix_course_section_contents_course_id", table_name="course_section_contents")
    op.drop_table("course_section_contents")

    op.drop_index("ix_course_sections_status", table_name="course_sections")
    op.drop_index("ix_course_sections_slug", table_name="course_sections")
    op.drop_index("ix_course_sections_position", table_name="course_sections")
    op.drop_index("ix_course_sections_course_id", table_name="course_sections")
    op.drop_table("course_sections")

    op.drop_index("ix_courses_status", table_name="courses")
    op.drop_index("ix_courses_subject", table_name="courses")
    op.drop_index("ix_courses_topic_slug", table_name="courses")
    op.drop_index("ix_courses_learner_id", table_name="courses")
    op.drop_table("courses")
