from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.domain import Concept, ContentSnippet, GenerationTrace, Learner, LessonPlan, LessonPlanStep
from app.services.llm import LlmError, LlmProvider
from app.services.repositories import LessonPlanRepository


class LessonPlanStepPayload(BaseModel):
    title: str
    objective_id: str | None = None
    objective_slug: str | None = None
    instruction: str
    rationale: str
    step_type: str = Field(pattern="^(explain|diagnostic|practice|review|advance)$")


class LessonPlanPayload(BaseModel):
    summary: str
    steps: list[LessonPlanStepPayload] = Field(min_length=3, max_length=6)


class LessonPlannerService:
    PROMPT_VERSION = "lesson_plan_v1"
    FALLBACK_PROMPT_VERSION = "lesson_plan_fallback_v1"

    def __init__(self, lesson_plan_repository: LessonPlanRepository, llm_provider: LlmProvider) -> None:
        self.lesson_plan_repository = lesson_plan_repository
        self.llm_provider = llm_provider
        self.logger = logging.getLogger(__name__)

    def get_or_create_plan(
        self,
        learner: Learner,
        concept: Concept,
        content_snippets: list[ContentSnippet],
    ) -> LessonPlan:
        existing = self.lesson_plan_repository.get_active(learner.id, concept.slug)
        if existing is not None:
            return existing
        return self.create_plan(learner, concept, content_snippets)

    def create_plan(
        self,
        learner: Learner,
        concept: Concept,
        content_snippets: list[ContentSnippet],
    ) -> LessonPlan:
        snippet_summaries = "\n".join(
            f"- {snippet.title}: {snippet.summary}" for snippet in content_snippets[:3]
        ) or "- none"
        objective_lines = "\n".join(
            f"- id={objective.id} | slug={objective.slug} | title={objective.title} | description={objective.description}"
            for objective in concept.objectives
        ) or "- none"

        prompt_inputs = {
            "learner_id": learner.id,
            "topic": concept.slug,
            "objective_ids": [objective.id for objective in concept.objectives],
            "content_ids": [snippet.id for snippet in content_snippets],
        }
        prompt = (
            "Create a short lesson plan for an adaptive tutoring system.\n"
            "Return JSON only.\n"
            "The lesson plan should be practical for an interactive tutor session.\n"
            "Use 3 to 6 steps total. Include a mix of explanation, checking understanding, and practice.\n\n"
            f"Learner goal: {learner.goal}\n"
            f"Learner preferences: style={learner.learning_style.teaching_style}, "
            f"verbosity={learner.learning_style.verbosity}, prefers_examples={learner.learning_style.prefers_examples}\n"
            f"Topic: {concept.slug}\n"
            f"Topic description: {concept.description}\n"
            f"Objectives:\n{objective_lines}\n"
            f"Available content:\n{snippet_summaries}\n"
        )

        try:
            payload = self.llm_provider.generate_structured(
                prompt=prompt,
                schema=LessonPlanPayload,
                schema_name="lesson_plan",
            )
            trace = GenerationTrace(
                provider=self.llm_provider.provider_name,
                model=self.llm_provider.model_name,
                prompt_version=self.PROMPT_VERSION,
                prompt_inputs=prompt_inputs,
            )
        except LlmError as error:
            self.logger.warning(
                "Falling back to deterministic lesson plan learner_id=%s topic=%s error_type=%s",
                learner.id,
                concept.slug,
                type(error).__name__,
            )
            payload = self._build_fallback_payload(concept, content_snippets)
            trace = GenerationTrace(
                provider="system",
                model="fallback",
                prompt_version=self.FALLBACK_PROMPT_VERSION,
                prompt_inputs={**prompt_inputs, "error_type": type(error).__name__},
            )
        lesson_plan = LessonPlan(
            learner_id=learner.id,
            topic=concept.slug,
            summary=payload.summary,
            steps=[
                LessonPlanStep(
                    title=step.title,
                    objective_id=step.objective_id,
                    objective_slug=step.objective_slug,
                    instruction=step.instruction,
                    rationale=step.rationale,
                    step_type=step.step_type,
                )
                for step in payload.steps
            ],
            trace=trace,
        )
        self.lesson_plan_repository.supersede_active(learner.id, concept.slug)
        return self.lesson_plan_repository.save(lesson_plan)

    def _build_fallback_payload(
        self,
        concept: Concept,
        content_snippets: list[ContentSnippet],
    ) -> LessonPlanPayload:
        primary_objective = concept.objectives[0] if concept.objectives else None
        secondary_objective = concept.objectives[1] if len(concept.objectives) > 1 else primary_objective
        source_hint = content_snippets[0].title if content_snippets else concept.title

        steps = [
            LessonPlanStepPayload(
                title=f"Build intuition for {concept.title}",
                objective_id=primary_objective.id if primary_objective is not None else None,
                objective_slug=primary_objective.slug if primary_objective is not None else None,
                instruction=(
                    f"Start with a simple explanation of {concept.title.lower()} and connect it to a concrete example from {source_hint}."
                ),
                rationale="The learner needs a clear starting mental model before moving into checks or practice.",
                step_type="explain",
            ),
            LessonPlanStepPayload(
                title="Check understanding",
                objective_id=primary_objective.id if primary_objective is not None else None,
                objective_slug=primary_objective.slug if primary_objective is not None else None,
                instruction=(
                    "Ask one focused diagnostic question that reveals whether the core idea makes sense in the learner's own words."
                ),
                rationale="A quick diagnostic confirms whether the explanation actually landed.",
                step_type="diagnostic",
            ),
            LessonPlanStepPayload(
                title="Practice the weak spot",
                objective_id=secondary_objective.id if secondary_objective is not None else None,
                objective_slug=secondary_objective.slug if secondary_objective is not None else None,
                instruction=(
                    "Give one short practice or comparison task that targets the weakest subskill on this concept."
                ),
                rationale="Practice turns passive understanding into something the learner can actively use.",
                step_type="practice",
            ),
            LessonPlanStepPayload(
                title="Connect forward",
                objective_id=secondary_objective.id if secondary_objective is not None else None,
                objective_slug=secondary_objective.slug if secondary_objective is not None else None,
                instruction=(
                    "Summarize the main idea, correct any remaining confusion, and connect it to what comes next."
                ),
                rationale="Closing the loop helps retention and prepares the learner for advancement.",
                step_type="advance",
            ),
        ]
        return LessonPlanPayload(
            summary=f"A guided lesson in {concept.title} that builds intuition, checks understanding, and moves into practice.",
            steps=steps,
        )

    def advance_progress(
        self,
        lesson_plan: LessonPlan,
        *,
        action: str,
        correctness: float,
        focus_objective_id: str | None,
        topic_ready_to_advance: bool,
    ) -> LessonPlan:
        if not lesson_plan.steps:
            return lesson_plan

        current_index = min(max(lesson_plan.current_step_index, 0), len(lesson_plan.steps) - 1)
        current_step = lesson_plan.steps[current_index]

        should_complete = False
        if action == "advance" or topic_ready_to_advance:
            should_complete = True
        elif current_step.objective_id and current_step.objective_id == focus_objective_id and correctness >= 0.7:
            should_complete = True
        elif current_step.step_type in {"diagnostic", "practice", "review"} and correctness >= 0.75:
            should_complete = True
        elif current_step.step_type == "explain" and correctness >= 0.65:
            should_complete = True

        if should_complete and current_step.id not in lesson_plan.completed_step_ids:
            lesson_plan.completed_step_ids.append(current_step.id)

        while current_index < len(lesson_plan.steps) and lesson_plan.steps[current_index].id in lesson_plan.completed_step_ids:
            current_index += 1

        lesson_plan.current_step_index = min(current_index, len(lesson_plan.steps) - 1)
        lesson_plan.updated_at = datetime.now(UTC)
        return self.lesson_plan_repository.save(lesson_plan)
