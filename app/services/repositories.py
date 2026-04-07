from __future__ import annotations

from typing import Protocol

from pydantic import TypeAdapter
from sqlalchemy.orm import Session as DbSession

from app.models.api import CreateLearnerRequest, CreateSessionRequest
from app.models.domain import (
    Learner,
    LearningPreferences,
    Misconception,
    Session,
    TopicState,
    TutorTurn,
)
from app.services.orm import LearnerRecord, SessionRecord

topic_state_map_adapter = TypeAdapter(dict[str, TopicState])
misconceptions_adapter = TypeAdapter(list[Misconception])
turns_adapter = TypeAdapter(list[TutorTurn])


class LearnerRepository(Protocol):
    def create(self, payload: CreateLearnerRequest) -> Learner: ...
    def get(self, learner_id: str) -> Learner | None: ...
    def save(self, learner: Learner) -> Learner: ...


class SessionRepository(Protocol):
    def create(self, payload: CreateSessionRequest) -> Session: ...
    def get(self, session_id: str) -> Session | None: ...
    def save(self, session: Session) -> Session: ...


def _learner_from_record(record: LearnerRecord) -> Learner:
    return Learner(
        id=record.id,
        name=record.name,
        goal=record.goal,
        skills=topic_state_map_adapter.validate_python(record.skills or {}),
        misconceptions=misconceptions_adapter.validate_python(record.misconceptions or []),
        learning_style=LearningPreferences.model_validate(record.learning_style or {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _session_from_record(record: SessionRecord) -> Session:
    return Session(
        id=record.id,
        learner_id=record.learner_id,
        topic=record.topic,
        mode=record.mode,
        turns=turns_adapter.validate_python(record.turns or []),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class SqlLearnerRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def create(self, payload: CreateLearnerRequest) -> Learner:
        learner = Learner(
            name=payload.name,
            goal=payload.goal,
            learning_style=payload.preferences,
        )
        if payload.initial_topic:
            learner.skills[payload.initial_topic] = TopicState(mastery=0.2, confidence=0.2)

        record = LearnerRecord(
            id=learner.id,
            name=learner.name,
            goal=learner.goal,
            skills=learner.model_dump(mode="json")["skills"],
            misconceptions=learner.model_dump(mode="json")["misconceptions"],
            learning_style=learner.learning_style.model_dump(mode="json"),
            created_at=learner.created_at,
            updated_at=learner.updated_at,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return _learner_from_record(record)

    def get(self, learner_id: str) -> Learner | None:
        record = self.db.get(LearnerRecord, learner_id)
        if record is None:
            return None
        return _learner_from_record(record)

    def save(self, learner: Learner) -> Learner:
        record = self.db.get(LearnerRecord, learner.id)
        if record is None:
            raise ValueError(f"Learner {learner.id} not found")

        learner_payload = learner.model_dump(mode="json")
        record.name = learner.name
        record.goal = learner.goal
        record.skills = learner_payload["skills"]
        record.misconceptions = learner_payload["misconceptions"]
        record.learning_style = learner.learning_style.model_dump(mode="json")
        record.created_at = learner.created_at
        record.updated_at = learner.updated_at

        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return _learner_from_record(record)


class SqlSessionRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def create(self, payload: CreateSessionRequest) -> Session:
        session = Session(
            learner_id=payload.learner_id,
            topic=payload.topic,
            mode=payload.mode,
        )

        record = SessionRecord(
            id=session.id,
            learner_id=session.learner_id,
            topic=session.topic,
            mode=session.mode.value,
            turns=[],
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return _session_from_record(record)

    def get(self, session_id: str) -> Session | None:
        record = self.db.get(SessionRecord, session_id)
        if record is None:
            return None
        return _session_from_record(record)

    def save(self, session: Session) -> Session:
        record = self.db.get(SessionRecord, session.id)
        if record is None:
            raise ValueError(f"Session {session.id} not found")

        session_payload = session.model_dump(mode="json")
        record.topic = session.topic
        record.mode = session.mode.value
        record.turns = session_payload["turns"]
        record.created_at = session.created_at
        record.updated_at = session.updated_at

        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return _session_from_record(record)
