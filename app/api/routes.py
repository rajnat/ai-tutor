from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.models.api import (
    AccountResponse,
    AuthResponse,
    CompleteReviewRequest,
    ConceptResponse,
    CreateConceptRequest,
    CreateLearnerRequest,
    CreateSessionRequest,
    LearnerResponse,
    LessonPlanResponse,
    LoginRequest,
    SupplementalMaterialResponse,
    SignupRequest,
    TopicProgressResponse,
    ReviewResponse,
    SessionResponse,
    SubmitTurnRequest,
    SubmitTurnResponse,
)
from app.models.domain import Account, AuthSession, Concept
from app.services.database import get_db_session
from app.services.curriculum import CurriculumPlanner
from app.services.dependencies import (
    get_account_repository,
    get_auth_service,
    get_current_account,
    get_curriculum_repository,
    get_learner_repository,
    get_lesson_plan_repository,
    get_material_service,
    get_orchestrator,
    get_progress_service,
    get_review_repository,
    get_session_repository,
)
from app.services.objectives import ObjectiveGenerator
from app.services.review import ReviewScheduler
from app.services.lesson_planner import LessonPlannerService
from app.services.content_library import ContentLibraryService

api_router = APIRouter(prefix="/api/v1")


@api_router.post("/auth/signup", response_model=AuthResponse)
def signup(payload: SignupRequest, db: DbSession = Depends(get_db_session)) -> AuthResponse:
    account_repository = get_account_repository(db)
    auth_service = get_auth_service()
    existing = account_repository.get_by_email(payload.email.lower())
    if existing is not None:
        raise HTTPException(status_code=409, detail="Account already exists")

    learner = get_learner_repository(db).create(
        CreateLearnerRequest(
            name=payload.name,
            goal=payload.goal,
            initial_topic=payload.initial_topic,
        )
    )
    account = account_repository.create(
        Account(email=payload.email.lower(), learner_id=learner.id),
        password_hash=auth_service.hash_password(payload.password),
    )
    token, token_hash, expires_at = auth_service.issue_session_token()
    account_repository.create_session(
        AuthSession(account_id=account.id, token=token, expires_at=expires_at),
        token_hash=token_hash,
    )
    return AuthResponse(
        token=token,
        account=AccountResponse.model_validate(account),
        learner=LearnerResponse.model_validate(learner),
    )


@api_router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: DbSession = Depends(get_db_session)) -> AuthResponse:
    account_repository = get_account_repository(db)
    auth_service = get_auth_service()
    result = account_repository.get_by_email(payload.email.lower())
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    account, password_hash = result
    if not auth_service.verify_password(payload.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    learner = get_learner_repository(db).get(account.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    token, token_hash, expires_at = auth_service.issue_session_token()
    account_repository.create_session(
        AuthSession(account_id=account.id, token=token, expires_at=expires_at),
        token_hash=token_hash,
    )
    return AuthResponse(
        token=token,
        account=AccountResponse.model_validate(account),
        learner=LearnerResponse.model_validate(learner),
    )


@api_router.get("/auth/me", response_model=AuthResponse)
def auth_me(
    current_account: tuple[str, str] = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> AuthResponse:
    account_id, learner_id = current_account
    account = get_account_repository(db).get(account_id)
    learner = get_learner_repository(db).get(learner_id)
    if account is None or learner is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return AuthResponse(
        token="",
        account=AccountResponse.model_validate(account),
        learner=LearnerResponse.model_validate(learner),
    )


@api_router.post("/auth/logout")
def logout(
    current_account: tuple[str, str] = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    del current_account
    if authorization and authorization.startswith("Bearer "):
        get_account_repository(db).revoke_session(get_auth_service().hash_token(authorization.removeprefix("Bearer ").strip()))
    return {"status": "ok"}


@api_router.post("/learners", response_model=LearnerResponse)
def create_learner(
    payload: CreateLearnerRequest, db: DbSession = Depends(get_db_session)
) -> LearnerResponse:
    learner = get_learner_repository(db).create(payload)
    return LearnerResponse.model_validate(learner)


@api_router.get("/learners/{learner_id}", response_model=LearnerResponse)
def get_learner(
    learner_id: str,
    current_account: tuple[str, str] = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> LearnerResponse:
    _, current_learner_id = current_account
    if learner_id != current_learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    return LearnerResponse.model_validate(learner)


@api_router.get("/learners/{learner_id}/progress/objectives", response_model=list[TopicProgressResponse])
def get_objective_progress(
    learner_id: str,
    subject: str | None = None,
    current_account: tuple[str, str] = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> list[TopicProgressResponse]:
    _, current_learner_id = current_account
    if learner_id != current_learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
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
    current_account: tuple[str, str] = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> list[SupplementalMaterialResponse]:
    _, current_learner_id = current_account
    if learner_id != current_learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    concept = get_curriculum_repository(db).get_by_slug(topic)
    focus_objective = CurriculumPlanner().weakest_objective(learner, concept)
    suggestions = get_material_service().suggest(topic=topic, concept=concept, focus_objective=focus_objective)
    return [SupplementalMaterialResponse.model_validate(item) for item in suggestions]


@api_router.get("/learners/{learner_id}/reviews/due", response_model=list[ReviewResponse])
def get_due_reviews(
    learner_id: str,
    current_account: tuple[str, str] = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> list[ReviewResponse]:
    _, current_learner_id = current_account
    if learner_id != current_learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    reviews = get_review_repository(db).get_due_reviews(learner_id)
    return [ReviewResponse.model_validate(review) for review in reviews]


@api_router.get("/learners/{learner_id}/curriculum/recommendations", response_model=list[ConceptResponse])
def get_curriculum_recommendations(
    learner_id: str,
    subject: str | None = None,
    current_account: tuple[str, str] = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> list[ConceptResponse]:
    _, current_learner_id = current_account
    if learner_id != current_learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    concepts = get_curriculum_repository(db).list_concepts(subject=subject)
    recommendations = CurriculumPlanner().suggest_next_topic(learner, concepts)
    return [ConceptResponse.model_validate(concept) for concept in recommendations]


@api_router.get("/learners/{learner_id}/lesson-plan", response_model=LessonPlanResponse)
def get_lesson_plan(
    learner_id: str,
    topic: str,
    current_account: tuple[str, str] = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> LessonPlanResponse:
    _, current_learner_id = current_account
    if learner_id != current_learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    concept = get_curriculum_repository(db).get_by_slug(topic)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")

    lesson_plan_repository = get_lesson_plan_repository(db)
    lesson_plan = lesson_plan_repository.get_active(learner_id, topic)
    if lesson_plan is None:
        content_snippets = ContentLibraryService().retrieve(topic_slug=topic, limit=3)
        lesson_plan = LessonPlannerService(
            lesson_plan_repository=lesson_plan_repository,
            llm_provider=get_orchestrator(db).lesson_planner.llm_provider,
        ).create_plan(learner=learner, concept=concept, content_snippets=content_snippets)
    return LessonPlanResponse.model_validate(lesson_plan)


@api_router.post("/sessions", response_model=SessionResponse)
def create_session(
    payload: CreateSessionRequest,
    current_account: tuple[str, str] = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> SessionResponse:
    _, current_learner_id = current_account
    if payload.learner_id != current_learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(payload.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    session = get_session_repository(db).create(payload)
    return SessionResponse.model_validate(session)


@api_router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    current_account: tuple[str, str] = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> SessionResponse:
    session = get_session_repository(db).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    _, current_learner_id = current_account
    if session.learner_id != current_learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return SessionResponse.model_validate(session)


@api_router.post("/sessions/{session_id}/turns", response_model=SubmitTurnResponse)
def submit_turn(
    session_id: str,
    payload: SubmitTurnRequest,
    current_account: tuple[str, str] = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> SubmitTurnResponse:
    session = get_session_repository(db).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    _, current_learner_id = current_account
    if session.learner_id != current_learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")

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
    current_account: tuple[str, str] = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> ReviewResponse:
    review = get_review_repository(db).get(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    _, current_learner_id = current_account
    if review.learner_id != current_learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    updated = ReviewScheduler().complete_review(review, correct=payload.correct)
    saved = get_review_repository(db).save(updated)
    return ReviewResponse.model_validate(saved)
