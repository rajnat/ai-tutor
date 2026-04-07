from pydantic import BaseModel, ConfigDict, Field

from app.models.domain import (
    EvaluationResult,
    Learner,
    LearningPreferences,
    Session,
    SessionMode,
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
