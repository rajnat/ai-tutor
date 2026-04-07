from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class TutorAction(str, Enum):
    EXPLAIN = "explain"
    ASK_DIAGNOSTIC = "ask_diagnostic"
    ASK_PRACTICE = "ask_practice"
    REINFORCE = "reinforce"
    ADVANCE = "advance"


class SessionMode(str, Enum):
    LEARN = "learn"
    ASK = "ask"
    TEST = "test"
    REVIEW = "review"


class TopicState(BaseModel):
    mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    last_practiced_at: datetime | None = None


class Misconception(BaseModel):
    topic: str
    description: str
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)


class LearningPreferences(BaseModel):
    verbosity: Literal["low", "medium", "high"] = "medium"
    prefers_examples: bool = True
    teaching_style: Literal["socratic", "direct", "blended"] = "blended"


class Learner(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    goal: str
    skills: dict[str, TopicState] = Field(default_factory=dict)
    misconceptions: list[Misconception] = Field(default_factory=list)
    learning_style: LearningPreferences = Field(default_factory=LearningPreferences)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EvaluationResult(BaseModel):
    correctness: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    misconception_detected: bool = False
    misconception_description: str | None = None
    reasoning: str


class TutorTurn(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    learner_message: str
    tutor_action: TutorAction
    tutor_response: str
    evaluation: EvaluationResult
    created_at: datetime = Field(default_factory=utc_now)


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    learner_id: str
    topic: str
    mode: SessionMode = SessionMode.LEARN
    turns: list[TutorTurn] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
