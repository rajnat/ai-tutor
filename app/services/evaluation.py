from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.models.domain import ConceptObjective, EvaluationResult, GenerationTrace
from app.services.llm import LlmProvider


class Evaluator(Protocol):
    def evaluate(
        self,
        learner_message: str,
        topic: str,
        objectives: list[ConceptObjective] | None = None,
    ) -> EvaluationResult: ...


class LlmEvaluationPayload(BaseModel):
    correctness: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    objective_id: str | None = None
    misconception_detected: bool = False
    misconception_description: str | None = None
    reasoning: str


class OpenAIEvaluationService:
    PROMPT_VERSION = "evaluation_v2"

    def __init__(self, llm_provider: LlmProvider) -> None:
        self.llm_provider = llm_provider

    def evaluate(
        self,
        learner_message: str,
        topic: str,
        objectives: list[ConceptObjective] | None = None,
    ) -> EvaluationResult:
        objectives = objectives or []
        objective_lines = "\n".join(
            f"- id={objective.id} | title={objective.title} | description={objective.description}"
            for objective in objectives
        ) or "- none"

        prompt_inputs = {
            "topic": topic,
            "objective_ids": [objective.id for objective in objectives],
            "learner_message": learner_message,
        }
        prompt = (
            "You are evaluating a learner response for an adaptive tutoring system.\n"
            "Return JSON only.\n"
            "Score the learner's demonstrated understanding, not politeness or fluency.\n"
            "Choose objective_id from the provided objectives when possible.\n"
            "If no objective clearly matches, return null.\n"
            "Set misconception_detected to true only when the answer reveals a concrete misunderstanding.\n\n"
            f"Topic: {topic}\n"
            f"Objectives:\n{objective_lines}\n\n"
            f"Learner response:\n{learner_message}"
        )

        payload = self.llm_provider.generate_structured(
            prompt=prompt,
            schema=LlmEvaluationPayload,
            schema_name="learner_evaluation",
        )
        objective_ids = {objective.id for objective in objectives}
        objective_id = payload.objective_id if payload.objective_id in objective_ids else None
        return EvaluationResult(
            correctness=payload.correctness,
            confidence=payload.confidence,
            objective_id=objective_id,
            misconception_detected=payload.misconception_detected,
            misconception_description=payload.misconception_description,
            reasoning=payload.reasoning,
            trace=GenerationTrace(
                provider=self.llm_provider.provider_name,
                model=self.llm_provider.model_name,
                prompt_version=self.PROMPT_VERSION,
                prompt_inputs=prompt_inputs,
            ),
        )
