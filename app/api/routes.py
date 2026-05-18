import logging
import threading
import time
from collections import defaultdict
from functools import lru_cache

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session as DbSession

from app.models.api import (
    ActivateSectionRequest,
    ActivateSectionResponse,
    AccountResponse,
    AuthResponse,
    CompleteReviewRequest,
    ConceptResponse,
    CreateStudySessionRequest,
    CreateConceptRequest,
    CreateLearnerRequest,
    CreateSessionRequest,
    LearnerResponse,
    LessonPlanResponse,
    LessonWorkspaceResponse,
    LoginRequest,
    CheckpointAttemptResponse,
    SubmitCheckpointAttemptRequest,
    SupplementalMaterialResponse,
    SignupRequest,
    TopicProgressResponse,
    ReviewResponse,
    SessionResponse,
    SubmitTurnRequest,
    SubmitTurnResponse,
    StudySessionResponse,
)
from app.models.domain import Account, AuthSession, Concept, SessionMode
from app.core.config import get_settings
from app.services.bootstrap import ensure_starter_curriculum
from app.services.database import get_db_session
from app.services.curriculum import CurriculumPlanner
from app.services.dependencies import (
    get_account_repository,
    require_admin_account,
    require_csrf,
    get_auth_service,
    get_current_account,
    get_course_workspace_service,
    get_curriculum_repository,
    get_learner_repository,
    get_lesson_plan_repository,
    get_material_service,
    get_orchestrator,
    get_progress_service,
    get_review_repository,
    get_session_repository,
    get_study_intent_service,
)
from app.services.lesson_planner import LessonPlannerService
from app.services.learner_model import LearnerModelService
from app.services.llm import LlmError
from app.services.objectives import ObjectiveGenerator
from app.services.review import ReviewScheduler
from app.services.tutor_config import DEFAULT_CONFIG

api_router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)

_login_attempts: dict[str, list[float]] = defaultdict(list)
_login_attempts_lock = threading.Lock()
_RATE_LIMIT_WINDOW_SECONDS = 300
_RATE_LIMIT_MAX_ATTEMPTS = 10


@lru_cache(maxsize=1)
def _admin_email_set() -> frozenset[str]:
    settings = get_settings()
    return frozenset(
        email.strip().lower()
        for email in settings.admin_email_allowlist.split(",")
        if email.strip()
    )


def _check_login_rate_limit(email: str) -> None:
    """Reject after 10 failed-or-attempted logins in a 5-minute window.

    NOTE: In-memory only — resets on restart and does not work across
    multiple worker processes. Replace with a Redis-backed solution for
    production multi-worker deployments.
    """
    key = email.lower()
    now = time.monotonic()
    with _login_attempts_lock:
        cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
        _login_attempts[key] = [t for t in _login_attempts[key] if t > cutoff]
        if len(_login_attempts[key]) >= _RATE_LIMIT_MAX_ATTEMPTS:
            raise HTTPException(status_code=429, detail="Too many login attempts")
        _login_attempts[key].append(now)


def _set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=settings.auth_session_days * 24 * 60 * 60,
        path="/",
    )


def _set_csrf_cookie(response: Response, csrf_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=settings.auth_session_days * 24 * 60 * 60,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_csrf_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _ensure_curriculum_seeded(db: DbSession) -> None:
    ensure_starter_curriculum(get_curriculum_repository(db))


def _normalize_topic_for_learner(db: DbSession, learner_id: str, requested_topic: str) -> str:
    _ensure_curriculum_seeded(db)
    curriculum_repository = get_curriculum_repository(db)
    concept = curriculum_repository.get_by_slug(requested_topic)
    if concept is not None:
        return requested_topic

    learner = get_learner_repository(db).get(learner_id)
    concepts = curriculum_repository.list_concepts()
    recommendations = CurriculumPlanner().suggest_next_topic(learner, concepts) if learner is not None else concepts
    fallback = (recommendations[0].slug if recommendations else None) or "algebra"
    logger.warning(
        "Normalizing unknown topic for learner_id=%s requested_topic=%s fallback_topic=%s",
        learner_id,
        requested_topic,
        fallback,
    )
    return fallback


@api_router.post("/auth/signup", response_model=AuthResponse)
def signup(payload: SignupRequest, response: Response, db: DbSession = Depends(get_db_session)) -> AuthResponse:
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
        Account(
            email=payload.email.lower(),
            learner_id=learner.id,
            is_admin=payload.email.lower() in _admin_email_set(),
        ),
        password_hash=auth_service.hash_password(payload.password),
    )
    token, token_hash, expires_at = auth_service.issue_session_token()
    csrf_token = auth_service.issue_csrf_token()
    account_repository.create_session(
        AuthSession(account_id=account.id, token=token, expires_at=expires_at),
        token_hash=token_hash,
    )
    _set_auth_cookie(response, token)
    _set_csrf_cookie(response, csrf_token)
    return AuthResponse(
        token=token,
        account=AccountResponse.model_validate(account),
        learner=LearnerResponse.model_validate(learner),
    )


@api_router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: DbSession = Depends(get_db_session)) -> AuthResponse:
    _check_login_rate_limit(payload.email)
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
    csrf_token = auth_service.issue_csrf_token()
    account_repository.create_session(
        AuthSession(account_id=account.id, token=token, expires_at=expires_at),
        token_hash=token_hash,
    )
    _set_auth_cookie(response, token)
    _set_csrf_cookie(response, csrf_token)
    return AuthResponse(
        token=token,
        account=AccountResponse.model_validate(account),
        learner=LearnerResponse.model_validate(learner),
    )


@api_router.get("/auth/me", response_model=AuthResponse)
def auth_me(
    response: Response,
    current_account: Account = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> AuthResponse:
    account = get_account_repository(db).get(current_account.id)
    learner = get_learner_repository(db).get(current_account.learner_id)
    if account is None or learner is None:
        raise HTTPException(status_code=404, detail="Account not found")
    _set_csrf_cookie(response, get_auth_service().issue_csrf_token())
    return AuthResponse(
        token="",
        account=AccountResponse.model_validate(account),
        learner=LearnerResponse.model_validate(learner),
    )


@api_router.post("/auth/logout")
def logout(
    response: Response,
    current_account: Account = Depends(require_csrf),
    db: DbSession = Depends(get_db_session),
    authorization: str | None = Header(default=None),
    session_token: str | None = Cookie(default=None, alias="adaptive_tutor_session"),
) -> dict[str, str]:
    del current_account
    _clear_auth_cookie(response)
    _clear_csrf_cookie(response)
    token: str | None = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    elif session_token:
        token = session_token.strip()
    if token:
        get_account_repository(db).revoke_session(get_auth_service().hash_token(token))
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
    current_account: Account = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> LearnerResponse:
    if learner_id != current_account.learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    return LearnerResponse.model_validate(learner)


@api_router.post("/learners/{learner_id}/study-session", response_model=StudySessionResponse)
def create_study_session(
    learner_id: str,
    payload: CreateStudySessionRequest,
    current_account: Account = Depends(require_csrf),
    db: DbSession = Depends(get_db_session),
) -> StudySessionResponse:
    if learner_id != current_account.learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    try:
        updated_learner, concept, lesson_plan, session = get_study_intent_service(db).launch(
            learner=learner,
            prompt=payload.prompt,
            mode=payload.mode.value,
        )
    except LlmError as exc:
        raise HTTPException(status_code=502, detail="AI service unavailable — please try again shortly") from exc

    # Check whether the learner meets prerequisites for this concept.
    all_concepts = get_curriculum_repository(db).list_concepts()
    blocking = CurriculumPlanner().find_blocking_prerequisite(updated_learner, concept, all_concepts)
    if blocking is not None:
        # Redirect to a prerequisite placement quiz before the main lesson.
        get_lesson_plan_repository(db).supersede_active(updated_learner.id, concept.slug)
        session.placement_topic = concept.slug
        session.topic = blocking.slug
        session.mode = SessionMode.PLACEMENT
        session = get_session_repository(db).save(session)
        lesson_plan = None
        logger.info(
            "Redirecting study session to placement quiz learner_id=%s blocking_prereq=%s requested_topic=%s",
            learner_id,
            blocking.slug,
            concept.slug,
        )
    else:
        get_course_workspace_service(db).ensure_course(
            learner=updated_learner,
            concept=concept,
            lesson_plan=lesson_plan,
        )

    logger.info(
        "Created study session learner_id=%s topic=%s prompt=%s",
        learner_id,
        concept.slug,
        payload.prompt,
    )
    return StudySessionResponse(
        learner=LearnerResponse.model_validate(updated_learner),
        concept=ConceptResponse.model_validate(concept),
        lesson_plan=LessonPlanResponse.model_validate(lesson_plan) if lesson_plan is not None else None,
        session=SessionResponse.model_validate(session),
    )


@api_router.get("/learners/{learner_id}/progress/objectives", response_model=list[TopicProgressResponse])
def get_objective_progress(
    learner_id: str,
    subject: str | None = None,
    current_account: Account = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> list[TopicProgressResponse]:
    if learner_id != current_account.learner_id:
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
    current_account: Account = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> list[SupplementalMaterialResponse]:
    if learner_id != current_account.learner_id:
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
    current_account: Account = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> list[ReviewResponse]:
    if learner_id != current_account.learner_id:
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
    current_account: Account = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> list[ConceptResponse]:
    if learner_id != current_account.learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    _ensure_curriculum_seeded(db)
    concepts = get_curriculum_repository(db).list_concepts(subject=subject)
    recommendations = CurriculumPlanner().suggest_next_topic(learner, concepts)
    logger.info(
        "Loaded curriculum recommendations learner_id=%s subject=%s count=%s",
        learner_id,
        subject or "all",
        len(recommendations),
    )
    return [ConceptResponse.model_validate(concept) for concept in recommendations]


@api_router.get("/learners/{learner_id}/lesson-plan", response_model=LessonPlanResponse)
def get_lesson_plan(
    learner_id: str,
    topic: str,
    current_account: Account = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> LessonPlanResponse:
    if learner_id != current_account.learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    normalized_topic = _normalize_topic_for_learner(db, learner_id, topic)
    concept = get_curriculum_repository(db).get_by_slug(normalized_topic)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")

    lesson_plan_repository = get_lesson_plan_repository(db)
    lesson_plan = lesson_plan_repository.get_active(learner_id, normalized_topic)
    if lesson_plan is None:
        logger.info(
            "Generating lesson plan learner_id=%s topic=%s",
            learner_id,
            normalized_topic,
        )
        try:
            lesson_plan = LessonPlannerService(
                lesson_plan_repository=lesson_plan_repository,
                llm_provider=get_orchestrator(db).lesson_planner.llm_provider,
            ).create_plan(learner=learner, concept=concept, content_snippets=[])
        except LlmError as exc:
            raise HTTPException(status_code=502, detail="AI service unavailable — please try again shortly") from exc
    logger.info(
        "Loaded lesson plan learner_id=%s requested_topic=%s normalized_topic=%s step_count=%s",
        learner_id,
        topic,
        normalized_topic,
        len(lesson_plan.steps),
    )
    return LessonPlanResponse.model_validate(lesson_plan)


@api_router.get("/learners/{learner_id}/workspace", response_model=LessonWorkspaceResponse)
def get_lesson_workspace(
    learner_id: str,
    current_account: Account = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> LessonWorkspaceResponse:
    if learner_id != current_account.learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    sessions = get_session_repository(db).list_for_learner(learner_id, limit=1)
    if not sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[0]
    normalized_topic = _normalize_topic_for_learner(db, learner_id, session.topic)
    if normalized_topic != session.topic:
        session.topic = normalized_topic
        session = get_session_repository(db).save(session)
    concept = get_curriculum_repository(db).get_by_slug(session.topic)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    lesson_plan = get_lesson_plan_repository(db).get_active(learner_id, session.topic)
    if lesson_plan is None:
        lesson_plan = LessonPlannerService(
            lesson_plan_repository=get_lesson_plan_repository(db),
            llm_provider=get_orchestrator(db).lesson_planner.llm_provider,
        ).create_plan(learner=learner, concept=concept, content_snippets=[])
    course_workspace = get_course_workspace_service(db)
    course = course_workspace.ensure_course(
        learner=learner,
        concept=concept,
        lesson_plan=lesson_plan,
    )
    current_section = course_workspace.current_section(course)
    if current_section is None:
        raise HTTPException(status_code=404, detail="Course section not found")
    active_step = (
        lesson_plan.steps[current_section.position]
        if lesson_plan.steps and current_section.position < len(lesson_plan.steps)
        else None
    )
    try:
        section_content = course_workspace.get_or_create_section_content(
            course=course,
            section=current_section,
            learner=learner,
            concept=concept,
            lesson_plan=lesson_plan,
            active_step=active_step,
            recent_messages=[turn.learner_message for turn in session.turns[-3:]],
        )
    except LlmError as exc:
        raise HTTPException(status_code=502, detail="AI service unavailable — please try again shortly") from exc
    return LessonWorkspaceResponse(
        course=course,
        current_section=current_section,
        session=SessionResponse.model_validate(session),
        lesson_plan=LessonPlanResponse.model_validate(lesson_plan),
        active_step=active_step,
        section_content=section_content.content,
    )


@api_router.post(
    "/learners/{learner_id}/courses/{course_id}/sections/activate",
    response_model=ActivateSectionResponse,
)
def activate_course_section(
    learner_id: str,
    course_id: str,
    payload: ActivateSectionRequest,
    current_account: Account = Depends(require_csrf),
    db: DbSession = Depends(get_db_session),
) -> ActivateSectionResponse:
    if learner_id != current_account.learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    sessions = get_session_repository(db).list_for_learner(learner_id, limit=1)
    if not sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[0]
    concept = get_curriculum_repository(db).get_by_slug(_normalize_topic_for_learner(db, learner_id, session.topic))
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    lesson_plan = get_lesson_plan_repository(db).get_active(learner_id, concept.slug)
    if lesson_plan is None:
        raise HTTPException(status_code=404, detail="Lesson plan not found")
    course_workspace = get_course_workspace_service(db)
    course = course_workspace.ensure_course(
        learner=learner,
        concept=concept,
        lesson_plan=lesson_plan,
    )
    if course.id != course_id:
        raise HTTPException(status_code=404, detail="Course not found")
    try:
        course, lesson_plan = course_workspace.activate_section(
            course=course,
            lesson_plan=lesson_plan,
            section_id=payload.section_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    current_section = course_workspace.current_section(course)
    if current_section is None:
        raise HTTPException(status_code=404, detail="Course section not found")
    active_step = (
        lesson_plan.steps[current_section.position]
        if lesson_plan.steps and current_section.position < len(lesson_plan.steps)
        else None
    )
    try:
        section_content = course_workspace.get_or_create_section_content(
            course=course,
            section=current_section,
            learner=learner,
            concept=concept,
            lesson_plan=lesson_plan,
            active_step=active_step,
            recent_messages=[turn.learner_message for turn in session.turns[-3:]],
        )
    except LlmError as exc:
        raise HTTPException(status_code=502, detail="AI service unavailable — please try again shortly") from exc
    return ActivateSectionResponse(
        course=course,
        lesson_plan=LessonPlanResponse.model_validate(lesson_plan),
        current_section=current_section,
        section_content=section_content.content,
    )


@api_router.post("/sessions", response_model=SessionResponse)
def create_session(
    payload: CreateSessionRequest,
    current_account: Account = Depends(require_csrf),
    db: DbSession = Depends(get_db_session),
) -> SessionResponse:
    if payload.learner_id != current_account.learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(payload.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    normalized_topic = _normalize_topic_for_learner(db, learner.id, payload.topic)
    if normalized_topic != payload.topic:
        logger.info(
            "Rewriting session creation topic learner_id=%s requested_topic=%s normalized_topic=%s",
            learner.id,
            payload.topic,
            normalized_topic,
        )
    session = get_session_repository(db).create(payload.model_copy(update={"topic": normalized_topic}))
    return SessionResponse.model_validate(session)


@api_router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    current_account: Account = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> SessionResponse:
    session = get_session_repository(db).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.learner_id != current_account.learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    normalized_topic = _normalize_topic_for_learner(db, session.learner_id, session.topic)
    if normalized_topic != session.topic:
        logger.info(
            "Repairing stale session topic session_id=%s learner_id=%s from=%s to=%s",
            session.id,
            session.learner_id,
            session.topic,
            normalized_topic,
        )
        session.topic = normalized_topic
        session = get_session_repository(db).save(session)
    return SessionResponse.model_validate(session)


@api_router.get("/learners/{learner_id}/sessions/latest", response_model=SessionResponse)
def get_latest_session(
    learner_id: str,
    current_account: Account = Depends(get_current_account),
    db: DbSession = Depends(get_db_session),
) -> SessionResponse:
    if learner_id != current_account.learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    sessions = get_session_repository(db).list_for_learner(learner_id, limit=1)
    if not sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[0]
    normalized_topic = _normalize_topic_for_learner(db, session.learner_id, session.topic)
    if normalized_topic != session.topic:
        logger.info(
            "Repairing latest session topic session_id=%s learner_id=%s from=%s to=%s",
            session.id,
            session.learner_id,
            session.topic,
            normalized_topic,
        )
        session.topic = normalized_topic
        session = get_session_repository(db).save(session)
    return SessionResponse.model_validate(session)


@api_router.post("/sessions/{session_id}/turns", response_model=SubmitTurnResponse)
def submit_turn(
    session_id: str,
    payload: SubmitTurnRequest,
    current_account: Account = Depends(require_csrf),
    db: DbSession = Depends(get_db_session),
) -> SubmitTurnResponse:
    session = get_session_repository(db).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.learner_id != current_account.learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    normalized_topic = _normalize_topic_for_learner(db, session.learner_id, session.topic)
    if normalized_topic != session.topic:
        logger.info(
            "Repairing session topic before turn session_id=%s learner_id=%s from=%s to=%s",
            session.id,
            session.learner_id,
            session.topic,
            normalized_topic,
        )
        session.topic = normalized_topic
        session = get_session_repository(db).save(session)

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
    payload: CreateConceptRequest,
    current_account: Account = Depends(require_csrf),
    db: DbSession = Depends(get_db_session),
) -> ConceptResponse:
    require_admin_account(current_account)
    existing = get_curriculum_repository(db).get_by_slug(payload.slug)
    if existing is not None:
        return ConceptResponse.model_validate(existing)
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
    current_account: Account = Depends(require_csrf),
    db: DbSession = Depends(get_db_session),
) -> ReviewResponse:
    review = get_review_repository(db).get(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.learner_id != current_account.learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    learner = get_learner_repository(db).get(review.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    concept = get_curriculum_repository(db).get_by_slug(review.topic)
    objectives = concept.objectives if concept is not None else []
    if review.objective_id is not None:
        objectives = [objective for objective in objectives if objective.id == review.objective_id]

    orchestrator = get_orchestrator(db)
    evaluation = orchestrator.evaluator.evaluate(
        learner_message=payload.answer,
        topic=review.topic,
        objectives=objectives,
    )
    updated_learner = orchestrator.learner_model.update_after_evaluation(
        learner=learner,
        topic=review.topic,
        correctness=evaluation.correctness,
        confidence=evaluation.confidence,
        misconception_description=evaluation.misconception_description,
    )
    if review.objective_id is not None:
        updated_learner.objective_states = orchestrator.objective_generator.ensure_states(
            updated_learner.objective_states,
            [review.objective_id],
        )
        updated_learner.objective_states = orchestrator.objective_generator.update_single_objective_state(
            updated_learner.objective_states,
            objective_id=review.objective_id,
            correctness=evaluation.correctness,
            confidence=evaluation.confidence,
        )
    get_learner_repository(db).save(updated_learner)

    updated = ReviewScheduler().complete_review(review, correctness=evaluation.correctness)
    saved = get_review_repository(db).save(updated)
    return ReviewResponse.model_validate(saved)


@api_router.post("/learners/{learner_id}/checkpoints/{checkpoint_id}/attempt", response_model=CheckpointAttemptResponse)
def submit_checkpoint_attempt(
    learner_id: str,
    checkpoint_id: str,
    payload: SubmitCheckpointAttemptRequest,
    current_account: Account = Depends(require_csrf),
    db: DbSession = Depends(get_db_session),
) -> CheckpointAttemptResponse:
    if learner_id != current_account.learner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    sessions = get_session_repository(db).list_for_learner(learner_id, limit=1)
    if not sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[0]
    concept = get_curriculum_repository(db).get_by_slug(_normalize_topic_for_learner(db, learner_id, session.topic))
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    lesson_plan = get_lesson_plan_repository(db).get_active(learner_id, concept.slug)
    if lesson_plan is None:
        raise HTTPException(status_code=404, detail="Lesson plan not found")
    course_workspace = get_course_workspace_service(db)
    course = course_workspace.ensure_course(
        learner=learner,
        concept=concept,
        lesson_plan=lesson_plan,
    )
    current_section = course_workspace.current_section(course)
    if current_section is None:
        raise HTTPException(status_code=404, detail="Course section not found")
    active_step = lesson_plan.steps[current_section.position] if lesson_plan.steps and current_section.position < len(lesson_plan.steps) else None
    try:
        section_content = course_workspace.get_or_create_section_content(
            course=course,
            section=current_section,
            learner=learner,
            concept=concept,
            lesson_plan=lesson_plan,
            active_step=active_step,
            recent_messages=[turn.learner_message for turn in session.turns[-3:]],
        )
    except LlmError as exc:
        raise HTTPException(status_code=502, detail="AI service unavailable — please try again shortly") from exc
    checkpoint = next(
        (
            block.checkpoint
            for block in section_content.content.blocks
            if block.checkpoint is not None and block.checkpoint.id == checkpoint_id
        ),
        None,
    )
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    is_correct = payload.selected_option_id == checkpoint.correct_option_id
    correctness = DEFAULT_CONFIG.checkpoint_correct_correctness if is_correct else DEFAULT_CONFIG.checkpoint_wrong_correctness
    confidence = DEFAULT_CONFIG.checkpoint_correct_confidence if is_correct else DEFAULT_CONFIG.checkpoint_wrong_confidence
    learner_model = LearnerModelService()
    updated_learner = learner_model.update_after_evaluation(
        learner=learner,
        topic=concept.slug,
        correctness=correctness,
        confidence=confidence,
        misconception_description=None if is_correct else checkpoint.explanation,
    )
    if checkpoint.objective_id is not None:
        objective_generator = ObjectiveGenerator()
        updated_learner.objective_states = objective_generator.ensure_states(
            updated_learner.objective_states,
            [checkpoint.objective_id],
        )
        updated_learner.objective_states = objective_generator.update_single_objective_state(
            updated_learner.objective_states,
            objective_id=checkpoint.objective_id,
            correctness=correctness,
            confidence=confidence,
        )
    updated_learner = get_learner_repository(db).save(updated_learner)
    course_workspace.record_checkpoint_attempt(
        learner_id=learner.id,
        course_id=course.id,
        session_id=session.id,
        checkpoint_id=checkpoint.id,
        selected_option_id=payload.selected_option_id,
        is_correct=is_correct,
        explanation=checkpoint.explanation,
    )
    course_workspace.advance_after_checkpoint(
        course=course,
        lesson_plan=lesson_plan,
        is_correct=is_correct,
    )

    # When the learner gets it wrong, regenerate section content so the next
    # view reflects the specific misconception and presents a fresh checkpoint
    # angle. We do this after saving the learner so misconceptions are included.
    if not is_correct:
        selected_option_text = next(
            (opt.text for opt in checkpoint.options if opt.id == payload.selected_option_id),
            None,
        )
        try:
            course_workspace.get_or_create_section_content(
                course=course,
                section=current_section,
                learner=updated_learner,
                concept=concept,
                lesson_plan=lesson_plan,
                active_step=active_step,
                recent_messages=[turn.learner_message for turn in session.turns[-3:]],
                force_regenerate=True,
                prior_wrong_answer=selected_option_text,
                prior_checkpoint_explanation=checkpoint.explanation,
            )
        except LlmError:
            # Regeneration failing is non-fatal — the learner still gets feedback.
            logger.warning(
                "Failed to regenerate section content after wrong checkpoint learner_id=%s checkpoint_id=%s",
                learner.id,
                checkpoint.id,
            )

    return CheckpointAttemptResponse(
        checkpoint_id=checkpoint.id,
        is_correct=is_correct,
        explanation=checkpoint.explanation,
        recommended_action="continue" if is_correct else "remediate",
        updated_learner=LearnerResponse.model_validate(updated_learner),
    )
