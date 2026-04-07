from sqlalchemy.orm import Session as DbSession

from app.services.curriculum import CurriculumPlanner
from app.services.evaluation import EvaluationService
from app.services.learner_model import LearnerModelService
from app.services.orchestrator import SessionOrchestrator
from app.services.repositories import SqlLearnerRepository, SqlSessionRepository
from app.services.teaching import TeachingService


def get_learner_repository(db: DbSession) -> SqlLearnerRepository:
    return SqlLearnerRepository(db)


def get_session_repository(db: DbSession) -> SqlSessionRepository:
    return SqlSessionRepository(db)


def get_orchestrator(db: DbSession) -> SessionOrchestrator:
    return SessionOrchestrator(
        learner_repository=get_learner_repository(db),
        session_repository=get_session_repository(db),
        learner_model=LearnerModelService(),
        evaluator=EvaluationService(),
        curriculum=CurriculumPlanner(),
        teacher=TeachingService(),
    )
