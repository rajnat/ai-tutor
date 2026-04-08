from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.domain import (
    Account,
    Concept,
    ConceptObjective,
    Course,
    CourseSection,
    EvaluationResult,
    LessonCheckpoint,
    LessonContentBlock,
    LessonSectionContent,
    Learner,
    LearningPreferences,
    LessonPlan,
    LessonPlanStep,
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
    goal: str = Field(default="Keep learning with Adaptive Tutor", min_length=1)
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
    answer: str = Field(min_length=1)


class SubmitCheckpointAttemptRequest(BaseModel):
    selected_option_id: str = Field(min_length=1)


class ActivateSectionRequest(BaseModel):
    section_id: str = Field(min_length=1)


class SignupRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)
    goal: str = Field(default="Keep learning with Adaptive Tutor", min_length=1)
    initial_topic: str | None = None


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)


class CreateStudySessionRequest(BaseModel):
    prompt: str = Field(min_length=3)
    mode: SessionMode = SessionMode.LEARN


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


class LessonPlanStepResponse(LessonPlanStep):
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
    active_lesson_step: LessonPlanStepResponse | None = None
    updated_learner: LearnerResponse
    updated_session: SessionResponse


class LessonCheckpointResponse(LessonCheckpoint):
    model_config = ConfigDict(from_attributes=True)


class LessonContentBlockResponse(LessonContentBlock):
    model_config = ConfigDict(from_attributes=True)


class LessonSectionContentResponse(LessonSectionContent):
    model_config = ConfigDict(from_attributes=True)


class CourseSectionResponse(CourseSection):
    model_config = ConfigDict(from_attributes=True)


class CourseResponse(Course):
    model_config = ConfigDict(from_attributes=True)


class LessonWorkspaceResponse(BaseModel):
    course: CourseResponse
    current_section: CourseSectionResponse | None = None
    session: SessionResponse
    lesson_plan: LessonPlanResponse
    active_step: LessonPlanStepResponse | None = None
    section_content: LessonSectionContentResponse


class CheckpointAttemptResponse(BaseModel):
    checkpoint_id: str
    is_correct: bool
    explanation: str
    recommended_action: str
    updated_learner: LearnerResponse


class ActivateSectionResponse(BaseModel):
    course: CourseResponse
    lesson_plan: LessonPlanResponse
    current_section: CourseSectionResponse | None = None
    section_content: LessonSectionContentResponse


class StudySessionResponse(BaseModel):
    learner: LearnerResponse
    concept: ConceptResponse
    lesson_plan: LessonPlanResponse
    session: SessionResponse
