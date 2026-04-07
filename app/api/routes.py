from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.models.api import (
    CompleteReviewRequest,
    ConceptResponse,
    CreateConceptRequest,
    CreateLearnerRequest,
    CreateSessionRequest,
    LearnerResponse,
    SupplementalMaterialResponse,
    TopicProgressResponse,
    ReviewResponse,
    SessionResponse,
    SubmitTurnRequest,
    SubmitTurnResponse,
)
from app.models.domain import Concept
from app.services.database import get_db_session
from app.services.curriculum import CurriculumPlanner
from app.services.dependencies import (
    get_curriculum_repository,
    get_learner_repository,
    get_material_service,
    get_orchestrator,
    get_progress_service,
    get_review_repository,
    get_session_repository,
)
from app.services.objectives import ObjectiveGenerator
from app.services.review import ReviewScheduler

api_router = APIRouter(prefix="/api/v1")


@api_router.post("/learners", response_model=LearnerResponse)
def create_learner(
    payload: CreateLearnerRequest, db: DbSession = Depends(get_db_session)
) -> LearnerResponse:
    learner = get_learner_repository(db).create(payload)
    return LearnerResponse.model_validate(learner)


@api_router.get("/learners/{learner_id}", response_model=LearnerResponse)
def get_learner(learner_id: str, db: DbSession = Depends(get_db_session)) -> LearnerResponse:
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    return LearnerResponse.model_validate(learner)


@api_router.get("/learners/{learner_id}/progress/objectives", response_model=list[TopicProgressResponse])
def get_objective_progress(
    learner_id: str,
    subject: str | None = None,
    db: DbSession = Depends(get_db_session),
) -> list[TopicProgressResponse]:
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    progress = get_progress_service(db).learner_topic_progress(learner, subject=subject)
    return [TopicProgressResponse.model_validate(item) for item in progress]


@api_router.get(
    "/learners/{learner_id}/materials/suggestions",
    response_model=list[SupplementalMaterialResponse],
)
def get_material_suggestions(
    learner_id: str,
    topic: str,
    db: DbSession = Depends(get_db_session),
) -> list[SupplementalMaterialResponse]:
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    concept = get_curriculum_repository(db).get_by_slug(topic)
    focus_objective = CurriculumPlanner().weakest_objective(learner, concept)
    suggestions = get_material_service().suggest(topic=topic, concept=concept, focus_objective=focus_objective)
    return [SupplementalMaterialResponse.model_validate(item) for item in suggestions]


@api_router.get("/learners/{learner_id}/reviews/due", response_model=list[ReviewResponse])
def get_due_reviews(learner_id: str, db: DbSession = Depends(get_db_session)) -> list[ReviewResponse]:
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    reviews = get_review_repository(db).get_due_reviews(learner_id)
    return [ReviewResponse.model_validate(review) for review in reviews]


@api_router.get("/learners/{learner_id}/curriculum/recommendations", response_model=list[ConceptResponse])
def get_curriculum_recommendations(
    learner_id: str,
    subject: str | None = None,
    db: DbSession = Depends(get_db_session),
) -> list[ConceptResponse]:
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    concepts = get_curriculum_repository(db).list_concepts(subject=subject)
    recommendations = CurriculumPlanner().suggest_next_topic(learner, concepts)
    return [ConceptResponse.model_validate(concept) for concept in recommendations]


@api_router.post("/sessions", response_model=SessionResponse)
def create_session(
    payload: CreateSessionRequest, db: DbSession = Depends(get_db_session)
) -> SessionResponse:
    learner = get_learner_repository(db).get(payload.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    session = get_session_repository(db).create(payload)
    return SessionResponse.model_validate(session)


@api_router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, db: DbSession = Depends(get_db_session)) -> SessionResponse:
    session = get_session_repository(db).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse.model_validate(session)


@api_router.post("/sessions/{session_id}/turns", response_model=SubmitTurnResponse)
def submit_turn(
    session_id: str,
    payload: SubmitTurnRequest,
    db: DbSession = Depends(get_db_session),
) -> SubmitTurnResponse:
    session = get_session_repository(db).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    learner = get_learner_repository(db).get(session.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    result = get_orchestrator(db).handle_turn(
        session_id=session_id,
        learner=learner,
        session=session,
        learner_message=payload.message,
        requested_mode=payload.mode,
    )
    return SubmitTurnResponse.model_validate(result)


@api_router.post("/curriculum/concepts", response_model=ConceptResponse)
def create_concept(
    payload: CreateConceptRequest, db: DbSession = Depends(get_db_session)
) -> ConceptResponse:
    objectives = ObjectiveGenerator().infer_objectives(
        concept_slug=payload.slug,
        concept_description=payload.description,
        objective_titles=payload.objectives,
    )
    concept = get_curriculum_repository(db).create_concept(
        Concept(
            slug=payload.slug,
            title=payload.title,
            description=payload.description,
            subject=payload.subject,
            prerequisites=payload.prerequisites,
            objectives=objectives,
        )
    )
    return ConceptResponse.model_validate(concept)


@api_router.post("/reviews/{review_id}/complete", response_model=ReviewResponse)
def complete_review(
    review_id: str,
    payload: CompleteReviewRequest,
    db: DbSession = Depends(get_db_session),
) -> ReviewResponse:
    review = get_review_repository(db).get(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")

    updated = ReviewScheduler().complete_review(review, correct=payload.correct)
    saved = get_review_repository(db).save(updated)
    return ReviewResponse.model_validate(saved)
