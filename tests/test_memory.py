from app.models.domain import (
    ConceptObjective,
    EvaluationResult,
    Learner,
    LearningPreferences,
    Misconception,
    Session,
    TutorAction,
    TutorTurn,
)
from app.services.memory import LearningMemoryService


class StubSessionRepository:
    def __init__(self, sessions: list[Session]) -> None:
        self.sessions = sessions

    def list_for_learner(self, learner_id: str, limit: int = 10) -> list[Session]:
        matching = [session for session in self.sessions if session.learner_id == learner_id]
        return matching[:limit]


def test_memory_service_collects_related_turns_and_misconceptions() -> None:
    learner = Learner(
        id="learner-1",
        name="Eswar",
        goal="Learn algebra",
        learning_style=LearningPreferences(),
        misconceptions=[
            Misconception(topic="algebra", description="Confuses variables with answers"),
        ],
    )
    current_session = Session(id="session-current", learner_id=learner.id, topic="algebra")
    prior_session = Session(
        id="session-prior",
        learner_id=learner.id,
        topic="algebra",
        turns=[
            TutorTurn(
                learner_message="Variables are confusing.",
                tutor_action=TutorAction.EXPLAIN,
                tutor_response="A variable stands for an unknown quantity.",
                evaluation=EvaluationResult(
                    correctness=0.4,
                    confidence=0.3,
                    objective_id="obj-1",
                    reasoning="Needs help.",
                ),
            ),
            TutorTurn(
                learner_message="So x is an unknown number.",
                tutor_action=TutorAction.ASK_PRACTICE,
                tutor_response="Good. Try solving for x now.",
                evaluation=EvaluationResult(
                    correctness=0.8,
                    confidence=0.7,
                    objective_id="obj-1",
                    reasoning="Solid understanding.",
                ),
            ),
        ],
    )

    memory_service = LearningMemoryService(StubSessionRepository([prior_session, current_session]))
    context = memory_service.build_context(
        learner=learner,
        topic="algebra",
        focus_objective=ConceptObjective(
            id="obj-1",
            slug="algebra:notation",
            title="Notation and vocabulary",
            description="Use algebraic symbols correctly.",
        ),
        current_session=current_session,
    )

    assert "Current weak objective" in context.summary
    assert context.misconception_notes == ["Confuses variables with answers"]
    assert any("Variables are confusing." in item for item in context.related_turns)
    assert context.prior_successes == ["So x is an unknown number."]
