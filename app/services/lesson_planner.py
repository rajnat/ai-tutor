from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.domain import Concept, ContentSnippet, GenerationTrace, Learner, LessonPlan, LessonPlanStep
from app.services.llm import LlmProvider
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

    def __init__(self, lesson_plan_repository: LessonPlanRepository, llm_provider: LlmProvider) -> None:
        self.lesson_plan_repository = lesson_plan_repository
        self.llm_provider = llm_provider

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

        payload = self.llm_provider.generate_structured(
            prompt=prompt,
            schema=LessonPlanPayload,
            schema_name="lesson_plan",
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
            trace=GenerationTrace(
                provider=self.llm_provider.provider_name,
                model=self.llm_provider.model_name,
                prompt_version=self.PROMPT_VERSION,
                prompt_inputs=prompt_inputs,
            ),
        )
        self.lesson_plan_repository.supersede_active(learner.id, concept.slug)
        return self.lesson_plan_repository.save(lesson_plan)

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
