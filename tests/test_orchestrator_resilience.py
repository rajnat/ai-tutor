from app.models.domain import Learner, LearningPreferences, Session, SessionMode
from app.services.curriculum import CurriculumPlanner
from app.services.llm import LlmUnavailableError
from app.services.objectives import ObjectiveGenerator
from app.services.orchestrator import SessionOrchestrator
from app.services.review import ReviewScheduler


class FakeLearnerRepository:
    def save(self, learner: Learner) -> Learner:
        return learner


class FakeSessionRepository:
    def save(self, session: Session) -> Session:
        return session


class FakeReviewRepository:
    def get_by_topic(self, learner_id: str, topic: str):
        return None

    def save(self, review_item):
        return review_item


class FakeCurriculumRepository:
    def get_by_slug(self, slug: str):
        return None

    def list_concepts(self):
        return []


class FakeLessonPlanRepository:
    def get_active(self, learner_id: str, topic: str):
        return None


class FakeMemoryService:
    def build_context(self, learner, topic, focus_objective, current_session):
        return None


class FakeContentLibrary:
    def retrieve(self, **kwargs):
        return []


class FakeLessonPlanner:
    def get_or_create_plan(self, learner, concept, content_snippets):
        raise AssertionError("should not be called when concept is missing")


class UnavailableEvaluator:
    def evaluate(self, learner_message: str, topic: str, objectives=None):
        raise LlmUnavailableError("provider down")


class UnavailableTeacher:
    def respond(self, **kwargs):
        raise LlmUnavailableError("provider down")


def test_orchestrator_gracefully_degrades_when_provider_is_unavailable() -> None:
    orchestrator = SessionOrchestrator(
        learner_repository=FakeLearnerRepository(),
        session_repository=FakeSessionRepository(),
        review_repository=FakeReviewRepository(),
        curriculum_repository=FakeCurriculumRepository(),
        lesson_plan_repository=FakeLessonPlanRepository(),
        memory_service=FakeMemoryService(),
        content_library=FakeContentLibrary(),
        lesson_planner=FakeLessonPlanner(),
        learner_model=__import__("app.services.learner_model", fromlist=["LearnerModelService"]).LearnerModelService(),
        evaluator=UnavailableEvaluator(),
        curriculum=CurriculumPlanner(),
        review_scheduler=ReviewScheduler(),
        objective_generator=ObjectiveGenerator(),
        teacher=UnavailableTeacher(),
    )

    learner = Learner(
        name="Eswar",
        goal="Learn algebra",
        learning_style=LearningPreferences(),
    )
    session = Session(
        learner_id=learner.id,
        topic="algebra",
        mode=SessionMode.LEARN,
    )

    response = orchestrator.handle_turn(
        session_id=session.id,
        learner=learner,
        session=session,
        learner_message="I am confused.",
        requested_mode=None,
    )

    assert response.evaluation.reasoning == "Evaluation unavailable because the language model could not be reached."
    assert "temporary issue" in response.tutor_response.lower()
    # No concept → no lesson plan → no active step; this is the correct degraded state.
    assert response.active_lesson_step is None
