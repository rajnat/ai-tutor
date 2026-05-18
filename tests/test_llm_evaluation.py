import httpx

from app.core.config import Settings
from app.models.domain import ConceptObjective
from app.services.evaluation import OpenAIEvaluationService
from app.services.llm import OpenAIResponsesProvider


def test_openai_provider_parses_structured_evaluation() -> None:
    response_payload = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            '{"correctness":0.82,"confidence":0.71,"objective_id":"obj-1",'
                            '"misconception_detected":false,"misconception_description":null,'
                            '"reasoning":"The learner explained the idea clearly and accurately."}'
                        ),
                    }
                ],
            }
        ]
    }

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=response_payload))
    provider = OpenAIResponsesProvider(
        Settings(
            llm_provider="openai",
            openai_api_key="test-key",
        ),
        http_client=httpx.Client(
            transport=transport,
            base_url="https://api.openai.com/v1",
        ),
    )

    evaluator = OpenAIEvaluationService(llm_provider=provider)
    result = evaluator.evaluate(
        learner_message="The notation uses symbols to represent quantities.",
        topic="algebra",
        objectives=[
            ConceptObjective(
                id="obj-1",
                slug="algebra:notation",
                title="Notation and vocabulary",
                description="Use algebraic symbols correctly.",
            )
        ],
        last_tutor_message="What do algebraic symbols represent?",
    )

    assert result.correctness == 0.82
    assert result.confidence == 0.71
    assert result.objective_id == "obj-1"
    assert result.misconception_detected is False
    assert result.trace is not None
    assert result.trace.provider == "openai"
    assert result.trace.prompt_version == "evaluation_v4"
