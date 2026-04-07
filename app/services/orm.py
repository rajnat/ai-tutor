from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.services.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class LearnerRecord(Base):
    __tablename__ = "learners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str] = mapped_column(Text())
    learning_style: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    topic_states: Mapped[list["LearnerTopicStateRecord"]] = relationship(
        back_populates="learner",
        cascade="all, delete-orphan",
    )
    objective_states: Mapped[list["LearnerObjectiveStateRecord"]] = relationship(
        back_populates="learner",
        cascade="all, delete-orphan",
    )
    misconceptions: Mapped[list["LearnerMisconceptionRecord"]] = relationship(
        back_populates="learner",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list["SessionRecord"]] = relationship(back_populates="learner")


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    learner_id: Mapped[str] = mapped_column(String(36), ForeignKey("learners.id"), index=True)
    topic: Mapped[str] = mapped_column(String(255), index=True)
    mode: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    learner: Mapped["LearnerRecord"] = relationship(back_populates="sessions")
    turns: Mapped[list["SessionTurnRecord"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionTurnRecord.created_at",
    )


class LearnerTopicStateRecord(Base):
    __tablename__ = "learner_topic_states"
    __table_args__ = (UniqueConstraint("learner_id", "topic", name="uq_learner_topic_states"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(String(36), ForeignKey("learners.id"), index=True)
    topic: Mapped[str] = mapped_column(String(255), index=True)
    mastery: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    learner: Mapped["LearnerRecord"] = relationship(back_populates="topic_states")


class LearnerObjectiveStateRecord(Base):
    __tablename__ = "learner_objective_states"
    __table_args__ = (
        UniqueConstraint("learner_id", "objective_id", name="uq_learner_objective_states"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(String(36), ForeignKey("learners.id"), index=True)
    objective_id: Mapped[str] = mapped_column(String(36), ForeignKey("concept_objectives.id"), index=True)
    mastery: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    learner: Mapped["LearnerRecord"] = relationship(back_populates="objective_states")


class LearnerMisconceptionRecord(Base):
    __tablename__ = "learner_misconceptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(String(36), ForeignKey("learners.id"), index=True)
    topic: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text())
    severity: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    learner: Mapped["LearnerRecord"] = relationship(back_populates="misconceptions")


class SessionTurnRecord(Base):
    __tablename__ = "session_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), index=True)
    learner_message: Mapped[str] = mapped_column(Text())
    tutor_action: Mapped[str] = mapped_column(String(32))
    tutor_response: Mapped[str] = mapped_column(Text())
    correctness: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    objective_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    misconception_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    misconception_description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    reasoning: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    session: Mapped["SessionRecord"] = relationship(back_populates="turns")


class ReviewItemRecord(Base):
    __tablename__ = "review_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    learner_id: Mapped[str] = mapped_column(String(36), ForeignKey("learners.id"), index=True)
    topic: Mapped[str] = mapped_column(String(255), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    interval_days: Mapped[int]
    review_count: Mapped[int]
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ConceptRecord(Base):
    __tablename__ = "concepts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text())
    subject: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    prerequisite_links: Mapped[list["ConceptPrerequisiteRecord"]] = relationship(
        back_populates="concept",
        cascade="all, delete-orphan",
        foreign_keys="ConceptPrerequisiteRecord.concept_id",
    )
    objectives: Mapped[list["ConceptObjectiveRecord"]] = relationship(
        back_populates="concept",
        cascade="all, delete-orphan",
        order_by="ConceptObjectiveRecord.slug",
    )


class ConceptPrerequisiteRecord(Base):
    __tablename__ = "concept_prerequisites"
    __table_args__ = (UniqueConstraint("concept_id", "prerequisite_id", name="uq_concept_prerequisite"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    concept_id: Mapped[str] = mapped_column(String(36), ForeignKey("concepts.id"), index=True)
    prerequisite_id: Mapped[str] = mapped_column(String(36), ForeignKey("concepts.id"), index=True)
    concept: Mapped["ConceptRecord"] = relationship(
        back_populates="prerequisite_links",
        foreign_keys=[concept_id],
    )


class ConceptObjectiveRecord(Base):
    __tablename__ = "concept_objectives"
    __table_args__ = (UniqueConstraint("concept_id", "slug", name="uq_concept_objective_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    concept_id: Mapped[str] = mapped_column(String(36), ForeignKey("concepts.id"), index=True)
    slug: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text())
    mastery_threshold: Mapped[float] = mapped_column(Float)
    concept: Mapped["ConceptRecord"] = relationship(back_populates="objectives")
