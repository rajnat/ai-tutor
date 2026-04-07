from sqlalchemy.orm import Session as DbSession

from app.services.curriculum import CurriculumPlanner
from app.services.evaluation import EvaluationService
from app.services.learner_model import LearnerModelService
from app.services.objectives import ObjectiveGenerator
from app.services.orchestrator import SessionOrchestrator
from app.services.progress import ProgressService
from app.services.repositories import (
    SqlCurriculumRepository,
    SqlLearnerRepository,
    SqlReviewRepository,
    SqlSessionRepository,
)
from app.services.materials import SupplementalMaterialService
from app.services.review import ReviewScheduler
from app.services.teaching import TeachingService


def get_learner_repository(db: DbSession) -> SqlLearnerRepository:
    return SqlLearnerRepository(db)


def get_session_repository(db: DbSession) -> SqlSessionRepository:
    return SqlSessionRepository(db)


def get_review_repository(db: DbSession) -> SqlReviewRepository:
    return SqlReviewRepository(db)


def get_curriculum_repository(db: DbSession) -> SqlCurriculumRepository:
    return SqlCurriculumRepository(db)


def get_progress_service(db: DbSession) -> ProgressService:
    return ProgressService(
        curriculum_repository=get_curriculum_repository(db),
        curriculum_planner=CurriculumPlanner(),
    )


def get_material_service() -> SupplementalMaterialService:
    return SupplementalMaterialService()


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
