from datetime import UTC, datetime

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from app.models.domain import Account, AuthSessionStatus
from app.services.course_workspace import CourseWorkspaceService
from app.services.auth import AuthService
from app.services.content_library import ContentLibraryService
from app.services.curriculum import CurriculumPlanner
from app.services.database import get_db_session
from app.services.evaluation import OpenAIEvaluationService
from app.services.learner_model import LearnerModelService
from app.services.lesson_planner import LessonPlannerService
from app.services.lesson_content import LessonContentService
from app.services.llm import OpenAIResponsesProvider, StubResponsesProvider
from app.services.memory import LearningMemoryService
from app.services.objectives import ObjectiveGenerator
from app.services.orchestrator import SessionOrchestrator
from app.services.progress import ProgressService
from app.services.repositories import (
    SqlAccountRepository,
    SqlCourseRepository,
    SqlCurriculumRepository,
    SqlLessonPlanRepository,
    SqlLearnerRepository,
    SqlReviewRepository,
    SqlSessionRepository,
)
from app.services.materials import SupplementalMaterialService
from app.services.review import ReviewScheduler
from app.services.teaching import OpenAITeachingService
from app.services.study_intent import StudyIntentService
from app.core.config import get_settings


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def get_learner_repository(db: DbSession) -> SqlLearnerRepository:
    return SqlLearnerRepository(db)


def get_session_repository(db: DbSession) -> SqlSessionRepository:
    return SqlSessionRepository(db)


def get_review_repository(db: DbSession) -> SqlReviewRepository:
    return SqlReviewRepository(db)


def get_curriculum_repository(db: DbSession) -> SqlCurriculumRepository:
    return SqlCurriculumRepository(db)


def get_lesson_plan_repository(db: DbSession) -> SqlLessonPlanRepository:
    return SqlLessonPlanRepository(db)


def get_account_repository(db: DbSession) -> SqlAccountRepository:
    return SqlAccountRepository(db)


def get_course_repository(db: DbSession) -> SqlCourseRepository:
    return SqlCourseRepository(db)


def get_progress_service(db: DbSession) -> ProgressService:
    return ProgressService(
        curriculum_repository=get_curriculum_repository(db),
        curriculum_planner=CurriculumPlanner(),
    )


def get_material_service() -> SupplementalMaterialService:
    return SupplementalMaterialService(ContentLibraryService())


def get_auth_service() -> AuthService:
    return AuthService()


def get_llm_provider():
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return OpenAIResponsesProvider(settings)
    if provider == "stub":
        return StubResponsesProvider()
    raise ValueError(f"Unsupported llm provider: {settings.llm_provider}")


def get_evaluator():
    return OpenAIEvaluationService(llm_provider=get_llm_provider())


def get_teacher():
    return OpenAITeachingService(llm_provider=get_llm_provider())


def get_current_account(
    authorization: str | None = Header(default=None),
    session_token: str | None = Cookie(default=None, alias="adaptive_tutor_session"),
    db: DbSession = Depends(get_db_session),
) -> Account:
    token: str | None = None
    if authorization is not None and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    elif session_token:
        token = session_token

    if not token:
        raise HTTPException(status_code=401, detail="Missing session")
    auth_service = get_auth_service()
    account_repository = get_account_repository(db)
    session = account_repository.get_session(auth_service.hash_token(token))
    if session is None or session.status != AuthSessionStatus.ACTIVE:
        raise HTTPException(status_code=401, detail="Invalid session")
    if _as_utc(session.expires_at) <= datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Session expired")

    account = account_repository.get(session.account_id)
    if account is None:
        raise HTTPException(status_code=401, detail="Account not found")
    return account


def require_admin_account(current_account: Account = Depends(get_current_account)) -> Account:
    if not current_account.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_account


def require_csrf(
    request: Request,
    current_account: Account = Depends(get_current_account),
) -> Account:
    settings = get_settings()
    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
    csrf_header = request.headers.get(settings.csrf_header_name)
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    return current_account


def get_orchestrator(db: DbSession) -> SessionOrchestrator:
    return SessionOrchestrator(
        learner_repository=get_learner_repository(db),
        session_repository=get_session_repository(db),
        review_repository=get_review_repository(db),
        curriculum_repository=get_curriculum_repository(db),
        lesson_plan_repository=get_lesson_plan_repository(db),
        memory_service=LearningMemoryService(get_session_repository(db)),
        content_library=ContentLibraryService(),
        lesson_planner=LessonPlannerService(
            lesson_plan_repository=get_lesson_plan_repository(db),
            llm_provider=get_llm_provider(),
        ),
        learner_model=LearnerModelService(),
        evaluator=get_evaluator(),
        curriculum=CurriculumPlanner(),
        review_scheduler=ReviewScheduler(),
        objective_generator=ObjectiveGenerator(),
        teacher=get_teacher(),
    )


def get_study_intent_service(db: DbSession) -> StudyIntentService:
    return StudyIntentService(
        curriculum_repository=get_curriculum_repository(db),
        learner_repository=get_learner_repository(db),
        session_repository=get_session_repository(db),
        lesson_planner=LessonPlannerService(
            lesson_plan_repository=get_lesson_plan_repository(db),
            llm_provider=get_llm_provider(),
        ),
        llm_provider=get_llm_provider(),
    )


def get_lesson_content_service() -> LessonContentService:
    return LessonContentService(llm_provider=get_llm_provider())


def get_course_workspace_service(db: DbSession) -> CourseWorkspaceService:
    return CourseWorkspaceService(
        course_repository=get_course_repository(db),
        lesson_plan_repository=get_lesson_plan_repository(db),
        lesson_content_service=get_lesson_content_service(),
    )
