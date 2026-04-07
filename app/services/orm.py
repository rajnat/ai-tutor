from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.services.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class LearnerRecord(Base):
    __tablename__ = "learners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str] = mapped_column(Text())
    skills: Mapped[dict] = mapped_column(JSON, default=dict)
    misconceptions: Mapped[list] = mapped_column(JSON, default=list)
    learning_style: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    learner_id: Mapped[str] = mapped_column(String(36), ForeignKey("learners.id"), index=True)
    topic: Mapped[str] = mapped_column(String(255), index=True)
    mode: Mapped[str] = mapped_column(String(32))
    turns: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
