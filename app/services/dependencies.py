from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.models.domain import AuthSessionStatus
from app.services.auth import AuthService
from app.services.curriculum import CurriculumPlanner
from app.services.database import get_db_session
from app.services.evaluation import EvaluationService
from app.services.learner_model import LearnerModelService
from app.services.objectives import ObjectiveGenerator
from app.services.orchestrator import SessionOrchestrator
from app.services.progress import ProgressService
from app.services.repositories import (
    SqlAccountRepository,
    SqlCurriculumRepository,
    SqlLearnerRepository,
    SqlReviewRepository,
    SqlSessionRepository,
)
from app.services.materials import SupplementalMaterialService
from app.services.review import ReviewScheduler
from app.services.teaching import TeachingService


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


def get_account_repository(db: DbSession) -> SqlAccountRepository:
    return SqlAccountRepository(db)


def get_progress_service(db: DbSession) -> ProgressService:
    return ProgressService(
        curriculum_repository=get_curriculum_repository(db),
        curriculum_planner=CurriculumPlanner(),
    )


def get_material_service() -> SupplementalMaterialService:
    return SupplementalMaterialService()


def get_auth_service() -> AuthService:
    return AuthService()


def get_current_account(
    authorization: str | None = Header(default=None),
    db: DbSession = Depends(get_db_session),
) -> tuple[str, str]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
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
    return account.id, account.learner_id


def get_orchestrator(db: DbSession) -> SessionOrchestrator:
    return SessionOrchestrator(
        learner_repository=get_learner_repository(db),
        session_repository=get_session_repository(db),
        review_repository=get_review_repository(db),
        curriculum_repository=get_curriculum_repository(db),
        learner_model=LearnerModelService(),
        evaluator=EvaluationService(),
        curriculum=CurriculumPlanner(),
        review_scheduler=ReviewScheduler(),
        objective_generator=ObjectiveGenerator(),
        teacher=TeachingService(),
    )
