import httpx

from app.core.config import Settings
from app.models.domain import (
    Concept,
    ConceptObjective,
    EvaluationResult,
    Learner,
    LearningPreferences,
    SessionMode,
    TutorAction,
    TutorTurn,
)
from app.services.llm import OpenAIResponsesProvider
from app.services.teaching import OpenAITeachingService


def test_openai_teaching_service_returns_model_text() -> None:
    response_payload = {
        "output_text": "Let's focus on notation first. What does the symbol x represent in this equation?"
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=response_payload))
    provider = OpenAIResponsesProvider(
        Settings(llm_provider="openai", openai_api_key="test-key"),
        http_client=httpx.Client(
            transport=transport,
            base_url="https://api.openai.com/v1",
        ),
    )

    teacher = OpenAITeachingService(llm_provider=provider)
    response = teacher.respond(
        learner=Learner(
            name="Eswar",
            goal="Learn algebra",
            learning_style=LearningPreferences(),
        ),
        topic="algebra",
        action=TutorAction.ASK_DIAGNOSTIC,
        learner_message="I think notation is confusing.",
        mode=SessionMode.LEARN,
        focus_objective=ConceptObjective(
            id="obj-1",
            slug="algebra:notation",
            title="Notation and vocabulary",
            description="Use algebraic symbols correctly.",
        ),
    )

    assert "notation" in response.text.lower()
    assert response.trace is not None
    assert response.trace.provider == "openai"
    assert response.trace.prompt_version == "teaching_v3"


class RecordingProvider:
    provider_name = "recording"
    model_name = "recording-model"

    def __init__(self) -> None:
        self.prompt = ""
        self.instructions = ""

    def generate_text(self, prompt: str, instructions: str | None = None) -> str:
        self.prompt = prompt
        self.instructions = instructions or ""
        return "Tutor response"


def test_teaching_prompt_includes_recent_turns_and_style_guidance() -> None:
    provider = RecordingProvider()
    teacher = OpenAITeachingService(llm_provider=provider)

    teacher.respond(
        learner=Learner(
            name="Eswar",
            goal="Learn algebra",
            learning_style=LearningPreferences(
                teaching_style="socratic",
                verbosity="high",
                prefers_examples=True,
            ),
        ),
        topic="algebra",
        action=TutorAction.REINFORCE,
        learner_message="I think variables are always equal to the answer.",
        mode=SessionMode.LEARN,
        current_concept=Concept(
            slug="algebra",
            title="Algebra Foundations",
            description="Core algebraic manipulation.",
            subject="math",
        ),
        focus_objective=ConceptObjective(
            id="obj-1",
            slug="algebra:notation",
            title="Notation and vocabulary",
            description="Use algebraic symbols correctly.",
        ),
        recent_turns=[
            TutorTurn(
                learner_message="I don't get what x means.",
                tutor_action=TutorAction.ASK_DIAGNOSTIC,
                tutor_response="What does x stand for in this expression?",
                evaluation=EvaluationResult(
                    correctness=0.3,
                    confidence=0.2,
                    objective_id="obj-1",
                    misconception_detected=False,
                    misconception_description=None,
                    reasoning="Uncertain answer.",
                ),
            ),
            TutorTurn(
                learner_message="I am confused by symbols.",
                tutor_action=TutorAction.EXPLAIN,
                tutor_response="Let's talk through what symbols stand for.",
                evaluation=EvaluationResult(
                    correctness=0.4,
                    confidence=0.3,
                    reasoning="Low confidence answer.",
                ),
            ),
            TutorTurn(
                learner_message="Maybe x is always the answer.",
                tutor_action=TutorAction.REINFORCE,
                tutor_response="Not quite. x is usually an unknown quantity, not automatically the answer.",
                evaluation=EvaluationResult(
                    correctness=0.25,
                    confidence=0.25,
                    objective_id="obj-1",
                    misconception_detected=True,
                    misconception_description="Confuses variable meaning with final answer.",
                    reasoning="Misconception present.",
                ),
            ),
            TutorTurn(
                learner_message="So x stands for an unknown number.",
                tutor_action=TutorAction.ASK_PRACTICE,
                tutor_response="Good. In 2x = 10, what would x be?",
                evaluation=EvaluationResult(
                    correctness=0.7,
                    confidence=0.6,
                    objective_id="obj-1",
                    misconception_detected=False,
                    misconception_description=None,
                    reasoning="Improving.",
                ),
            )
        ],
    )

    assert "recent_turns" in provider.prompt
    assert "session_summary" in provider.prompt
    assert "Low-confidence turns" in provider.prompt
    assert "I am confused by symbols." in provider.prompt
    assert "style_guidance: Keep exposition minimal" in provider.prompt
    assert "mode_guidance: Optimize for understanding and momentum" in provider.prompt
    assert "weak_objective_description: Use algebraic symbols correctly." in provider.prompt
    assert "Objective anchor: Notation and vocabulary." in provider.prompt
    assert "exactly one focused question" in provider.instructions
