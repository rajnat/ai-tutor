"""normalize learning state

Revision ID: 20260407_000002
Revises: 20260407_000001
Create Date: 2026-04-07 15:05:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "20260407_000002"
down_revision = "20260407_000001"
branch_labels = None
depends_on = None


def _deserialize(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def upgrade() -> None:
    op.create_table(
        "learner_topic_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("learner_id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("mastery", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("learner_id", "topic", name="uq_learner_topic_states"),
    )
    op.create_index(
        op.f("ix_learner_topic_states_learner_id"), "learner_topic_states", ["learner_id"], unique=False
    )
    op.create_index(op.f("ix_learner_topic_states_topic"), "learner_topic_states", ["topic"], unique=False)

    op.create_table(
        "learner_misconceptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("learner_id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_learner_misconceptions_learner_id"),
        "learner_misconceptions",
        ["learner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_learner_misconceptions_topic"), "learner_misconceptions", ["topic"], unique=False
    )

    op.create_table(
        "session_turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("learner_message", sa.Text(), nullable=False),
        sa.Column("tutor_action", sa.String(length=32), nullable=False),
        sa.Column("tutor_response", sa.Text(), nullable=False),
        sa.Column("correctness", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("misconception_detected", sa.Boolean(), nullable=False),
        sa.Column("misconception_description", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_session_turns_session_id"), "session_turns", ["session_id"], unique=False)

    bind = op.get_bind()
    learners = bind.execute(
        sa.text("SELECT id, skills, misconceptions FROM learners")
    ).mappings()
    for learner in learners:
        skills = _deserialize(learner["skills"]) or {}
        for topic, state in skills.items():
            bind.execute(
                sa.text(
                    """
                    INSERT INTO learner_topic_states
                    (learner_id, topic, mastery, confidence, last_practiced_at)
                    VALUES (:learner_id, :topic, :mastery, :confidence, :last_practiced_at)
                    """
                ),
                {
                    "learner_id": learner["id"],
                    "topic": topic,
                    "mastery": state.get("mastery", 0.0),
                    "confidence": state.get("confidence", 0.0),
                    "last_practiced_at": state.get("last_practiced_at"),
                },
            )

        misconceptions = _deserialize(learner["misconceptions"]) or []
        for item in misconceptions:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO learner_misconceptions
                    (learner_id, topic, description, severity, created_at)
                    VALUES (:learner_id, :topic, :description, :severity, :created_at)
                    """
                ),
                {
                    "learner_id": learner["id"],
                    "topic": item.get("topic", ""),
                    "description": item.get("description", ""),
                    "severity": item.get("severity", 0.5),
                    "created_at": item.get("created_at"),
                },
            )

    sessions = bind.execute(sa.text("SELECT id, turns FROM sessions")).mappings()
    for session in sessions:
        turns = _deserialize(session["turns"]) or []
        for turn in turns:
            evaluation = turn.get("evaluation", {})
            bind.execute(
                sa.text(
                    """
                    INSERT INTO session_turns
                    (id, session_id, learner_message, tutor_action, tutor_response,
                     correctness, confidence, misconception_detected,
                     misconception_description, reasoning, created_at)
                    VALUES (:id, :session_id, :learner_message, :tutor_action, :tutor_response,
                            :correctness, :confidence, :misconception_detected,
                            :misconception_description, :reasoning, :created_at)
                    """
                ),
                {
                    "id": turn.get("id"),
                    "session_id": session["id"],
                    "learner_message": turn.get("learner_message", ""),
                    "tutor_action": turn.get("tutor_action", "explain"),
                    "tutor_response": turn.get("tutor_response", ""),
                    "correctness": evaluation.get("correctness", 0.0),
                    "confidence": evaluation.get("confidence", 0.0),
                    "misconception_detected": evaluation.get("misconception_detected", False),
                    "misconception_description": evaluation.get("misconception_description"),
                    "reasoning": evaluation.get("reasoning", ""),
                    "created_at": turn.get("created_at"),
                },
            )

    with op.batch_alter_table("learners") as batch_op:
        batch_op.drop_column("skills")
        batch_op.drop_column("misconceptions")

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("turns")


def downgrade() -> None:
    with op.batch_alter_table("learners") as batch_op:
        batch_op.add_column(sa.Column("misconceptions", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("skills", sa.JSON(), nullable=False, server_default="{}"))

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(sa.Column("turns", sa.JSON(), nullable=False, server_default="[]"))

    op.drop_index(op.f("ix_session_turns_session_id"), table_name="session_turns")
    op.drop_table("session_turns")
    op.drop_index(op.f("ix_learner_misconceptions_topic"), table_name="learner_misconceptions")
    op.drop_index(op.f("ix_learner_misconceptions_learner_id"), table_name="learner_misconceptions")
    op.drop_table("learner_misconceptions")
    op.drop_index(op.f("ix_learner_topic_states_topic"), table_name="learner_topic_states")
    op.drop_index(op.f("ix_learner_topic_states_learner_id"), table_name="learner_topic_states")
    op.drop_table("learner_topic_states")
