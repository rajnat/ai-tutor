from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.domain import (
    Account,
    Concept,
    ConceptObjective,
    EvaluationResult,
    Learner,
    LearningPreferences,
    LessonPlan,
    ObjectiveProgress,
    ReviewItem,
    Session,
    SessionMode,
    SupplementalMaterial,
    TopicProgress,
    TutorAction,
)


class CreateLearnerRequest(BaseModel):
    name: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    initial_topic: str | None = None
    preferences: LearningPreferences = Field(default_factory=LearningPreferences)


class CreateSessionRequest(BaseModel):
    learner_id: str
    topic: str = Field(min_length=1)
    mode: SessionMode = SessionMode.LEARN


class SubmitTurnRequest(BaseModel):
    message: str = Field(min_length=1)
    mode: SessionMode | None = None


class CreateConceptRequest(BaseModel):
    slug: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    prerequisites: list[str] = Field(default_factory=list)
    objectives: list[str] | None = None


class CompleteReviewRequest(BaseModel):
    correct: bool


class SignupRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    initial_topic: str | None = None


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)


class AccountResponse(Account):
    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    token: str
    account: AccountResponse
    learner: LearnerResponse


class ReviewResponse(ReviewItem):
    model_config = ConfigDict(from_attributes=True)


class ConceptResponse(Concept):
    model_config = ConfigDict(from_attributes=True)


class ConceptObjectiveResponse(ConceptObjective):
    model_config = ConfigDict(from_attributes=True)


class ObjectiveProgressResponse(ObjectiveProgress):
    model_config = ConfigDict(from_attributes=True)


class TopicProgressResponse(TopicProgress):
    model_config = ConfigDict(from_attributes=True)


class LessonPlanResponse(LessonPlan):
    model_config = ConfigDict(from_attributes=True)


class SupplementalMaterialResponse(SupplementalMaterial):
    model_config = ConfigDict(from_attributes=True)


class LearnerResponse(Learner):
    model_config = ConfigDict(from_attributes=True)


class SessionResponse(Session):
    model_config = ConfigDict(from_attributes=True)


class SubmitTurnResponse(BaseModel):
    session_id: str
    tutor_action: TutorAction
    tutor_response: str
    evaluation: EvaluationResult
    updated_learner: LearnerResponse
    updated_session: SessionResponse
