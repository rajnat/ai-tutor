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
    PROMPT_VERSION = "evaluation_v3"

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
            "<task>\n"
            "Evaluate a learner response for tutoring state updates.\n"
            "Judge demonstrated understanding, not writing quality, confidence theater, or politeness.\n"
            "</task>\n\n"
            f"<topic>\n{topic}\n</topic>\n\n"
            f"<objectives>\n{objective_lines}\n</objectives>\n\n"
            f"<learner_response>\n{learner_message}\n</learner_response>\n\n"
            "<scoring_rubric>\n"
            "correctness:\n"
            "- 0.0 to 0.2 = off-topic, wrong, or empty understanding\n"
            "- 0.3 to 0.5 = partial but shaky understanding\n"
            "- 0.6 to 0.8 = mostly correct with useful understanding\n"
            "- 0.9 to 1.0 = clearly correct and well grounded\n"
            "confidence:\n"
            "- Estimate how confidently the learner seems to understand the idea, not their tone alone.\n"
            "objective_id:\n"
            "- Pick the one objective most evidenced by the response.\n"
            "- Return null if the response is too broad or no objective clearly matches.\n"
            "misconception_detected:\n"
            "- True only when the response reveals a specific conceptual misunderstanding, not just incompleteness.\n"
            "</scoring_rubric>"
        )
        instructions = (
            "You are a strict but fair tutoring evaluator.\n"
            "Return only JSON matching the schema.\n"
            "Be calibrated rather than generous.\n"
            "Use the provided objectives as the only valid source for objective_id.\n"
            "Keep reasoning short and diagnostic."
        )

        payload = self.llm_provider.generate_structured(
            prompt=prompt,
            schema=LlmEvaluationPayload,
            schema_name="learner_evaluation",
            instructions=instructions,
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
