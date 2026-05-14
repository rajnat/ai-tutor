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


class LearningPace(str, Enum):
    STRUGGLING = "struggling"
    NORMAL = "normal"
    ACCELERATING = "accelerating"


class AuthSessionStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


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


class Account(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    email: str
    learner_id: str
    is_admin: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class AuthSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    account_id: str
    token: str
    expires_at: datetime
    status: AuthSessionStatus = AuthSessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)


class GenerationTrace(BaseModel):
    provider: str
    model: str
    prompt_version: str
    prompt_inputs: dict = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    correctness: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    objective_id: str | None = None
    misconception_detected: bool = False
    misconception_description: str | None = None
    reasoning: str
    trace: GenerationTrace | None = None


class TeachingResponse(BaseModel):
    text: str
    trace: GenerationTrace | None = None


class CheckpointOption(BaseModel):
    id: str
    label: str
    text: str


class LessonCheckpoint(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: Literal["mcq", "short_answer"] = "mcq"
    prompt: str
    objective_id: str | None = None
    objective_slug: str | None = None
    options: list[CheckpointOption] = Field(default_factory=list)
    correct_option_id: str | None = None
    explanation: str


class LessonContentBlock(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: Literal["heading", "paragraph", "example", "checkpoint_mcq", "summary", "go_deeper"]
    text: str | None = None
    checkpoint: LessonCheckpoint | None = None
    prompts: list[str] = Field(default_factory=list)


class LessonSectionContent(BaseModel):
    title: str
    subtitle: str | None = None
    blocks: list[LessonContentBlock] = Field(default_factory=list)
    trace: GenerationTrace | None = None


class CourseStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class CourseSectionStatus(str, Enum):
    AVAILABLE = "available"
    ACTIVE = "active"
    COMPLETED = "completed"


class CourseSection(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    course_id: str
    position: int
    title: str
    slug: str
    summary: str
    objective_ids: list[str] = Field(default_factory=list)
    status: CourseSectionStatus = CourseSectionStatus.AVAILABLE


class CourseSectionContent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    course_id: str
    section_id: str
    content: LessonSectionContent
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Course(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    learner_id: str
    title: str
    study_prompt: str
    topic_slug: str
    subject: str
    status: CourseStatus = CourseStatus.ACTIVE
    current_section_id: str | None = None
    sections: list[CourseSection] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CheckpointAttempt(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    learner_id: str
    course_id: str
    session_id: str
    checkpoint_id: str
    selected_option_id: str
    is_correct: bool
    explanation: str
    created_at: datetime = Field(default_factory=utc_now)


class LearningMemoryContext(BaseModel):
    summary: str
    related_turns: list[str] = Field(default_factory=list)
    misconception_notes: list[str] = Field(default_factory=list)
    prior_successes: list[str] = Field(default_factory=list)


class ContentSnippet(BaseModel):
    id: str
    title: str
    topic_slug: str
    objective_slugs: list[str] = Field(default_factory=list)
    content_type: str
    difficulty: str
    source_name: str
    summary: str
    text: str
    estimated_minutes: int = 5


class LessonPlanStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    objective_id: str | None = None
    objective_slug: str | None = None
    instruction: str
    rationale: str
    step_type: Literal["explain", "diagnostic", "practice", "review", "advance"] = "explain"


class LessonPlan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    learner_id: str
    topic: str
    status: Literal["active", "superseded"] = "active"
    summary: str
    steps: list[LessonPlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    completed_step_ids: list[str] = Field(default_factory=list)
    trace: GenerationTrace | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TutorTurn(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    learner_message: str
    tutor_action: TutorAction
    tutor_response: str
    evaluation: EvaluationResult
    teaching_trace: GenerationTrace | None = None
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
    prompt: str
    objective_id: str | None = None
    objective_slug: str | None = None
    expected_answer: str | None = None
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
