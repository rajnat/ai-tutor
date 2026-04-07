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


class ReviewStatus(str, Enum):
    DUE = "due"
    SCHEDULED = "scheduled"


class TopicState(BaseModel):
    mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    last_practiced_at: datetime | None = None


class ObjectiveState(BaseModel):
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
    objective_states: dict[str, ObjectiveState] = Field(default_factory=dict)
    misconceptions: list[Misconception] = Field(default_factory=list)
    learning_style: LearningPreferences = Field(default_factory=LearningPreferences)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EvaluationResult(BaseModel):
    correctness: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    objective_id: str | None = None
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


class ReviewItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    learner_id: str
    topic: str
    due_at: datetime
    status: ReviewStatus = ReviewStatus.SCHEDULED
    interval_days: int = 1
    review_count: int = 0
    last_reviewed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Concept(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    slug: str
    title: str
    description: str
    subject: str
    prerequisites: list[str] = Field(default_factory=list)
    objectives: list["ConceptObjective"] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ConceptObjective(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    concept_id: str | None = None
    slug: str
    title: str
    description: str
    mastery_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class ObjectiveProgress(BaseModel):
    objective: ConceptObjective
    mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    last_practiced_at: datetime | None = None
    is_ready: bool = False


class TopicProgress(BaseModel):
    concept: Concept
    objectives: list[ObjectiveProgress] = Field(default_factory=list)
    concept_mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    concept_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ready_to_advance: bool = False


class SupplementalMaterial(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    material_type: Literal["reading", "video", "exercise", "comparison", "reflection"]
    description: str
    rationale: str
    query: str
