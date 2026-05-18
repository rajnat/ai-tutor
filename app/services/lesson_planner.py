from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.domain import Concept, ConceptObjective, ContentSnippet, GenerationTrace, Learner, LessonPlan, LessonPlanStep
from app.services.llm import LlmProvider
from app.services.repositories import LessonPlanRepository
from app.services.tutor_config import DEFAULT_CONFIG, TutorConfig


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
    PROMPT_VERSION = "lesson_plan_v3"

    def __init__(
        self,
        lesson_plan_repository: LessonPlanRepository,
        llm_provider: LlmProvider,
        config: TutorConfig = DEFAULT_CONFIG,
    ) -> None:
        self.lesson_plan_repository = lesson_plan_repository
        self.config = config
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
        prompt_inputs = {
            "learner_id": learner.id,
            "topic": concept.slug,
            "objective_ids": [objective.id for objective in concept.objectives],
            "content_ids": [snippet.id for snippet in content_snippets],
        }
        prompt = self._build_prompt(learner, concept, content_snippets)
        instructions = (
            "You are an expert instructional designer for adaptive tutoring.\n"
            "Return only JSON matching the schema.\n"
            "Prefer coherent instructional sequencing over broad topic coverage.\n"
            "Do not produce abstract syllabus language.\n"
            "Use the learner's current mastery state to personalize the plan — "
            "do not treat every learner as a blank slate."
        )

        payload = self.llm_provider.generate_structured(
            prompt=prompt,
            schema=LessonPlanPayload,
            schema_name="lesson_plan",
            instructions=instructions,
        )
        trace = GenerationTrace(
            provider=self.llm_provider.provider_name,
            model=self.llm_provider.model_name,
            prompt_version=self.PROMPT_VERSION,
            prompt_inputs=prompt_inputs,
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

    def _build_prompt(
        self,
        learner: Learner,
        concept: Concept,
        content_snippets: list[ContentSnippet],
    ) -> str:
        topic_state = learner.skills.get(concept.slug)
        topic_mastery = topic_state.mastery if topic_state is not None else 0.0

        mastered: list[str] = []
        learning: list[str] = []
        unstarted: list[str] = []

        objective_lines: list[str] = []
        for obj in concept.objectives:
            obj_state = learner.objective_states.get(obj.id)
            obj_mastery = obj_state.mastery if obj_state is not None else 0.0
            status = _objective_status(obj_mastery, obj.mastery_threshold)
            objective_lines.append(
                f"- id={obj.id} | slug={obj.slug} | title={obj.title}"
                f" | mastery={obj_mastery:.2f}/{obj.mastery_threshold:.2f} ({status})"
                f" | description={obj.description}"
            )
            if status == "MASTERED":
                mastered.append(f"{obj.title} ({obj_mastery:.2f}/{obj.mastery_threshold:.2f})")
            elif status == "LEARNING":
                learning.append(f"{obj.title} ({obj_mastery:.2f}/{obj.mastery_threshold:.2f})")
            else:
                unstarted.append(f"{obj.title} ({obj_mastery:.2f}/{obj.mastery_threshold:.2f})")

        objectives_block = "\n".join(objective_lines) or "- none"

        mastered_lines = "\n".join(f"    - {x}" for x in mastered) or "    - none"
        learning_lines = "\n".join(f"    - {x}" for x in learning) or "    - none"
        unstarted_lines = "\n".join(f"    - {x}" for x in unstarted) or "    - none"

        topic_mastery_label = _topic_mastery_label(topic_mastery)
        learner_state_block = (
            f"<learner_state>\n"
            f"topic_mastery: {topic_mastery:.2f} ({topic_mastery_label})\n"
            f"objective_status:\n"
            f"  MASTERED — omit or use one brief diagnostic only:\n{mastered_lines}\n"
            f"  LEARNING — needs continued work, allocate steps here:\n{learning_lines}\n"
            f"  UNSTARTED — needs full introduction:\n{unstarted_lines}\n"
            f"</learner_state>\n"
        )

        snippet_summaries = "\n".join(
            f"- {snippet.title}: {snippet.summary}" for snippet in content_snippets[:3]
        ) or "- none"

        # Build personalized starting-point guidance based on actual state.
        if all(m == 0.0 for m in [
            (learner.objective_states.get(o.id).mastery if learner.objective_states.get(o.id) else 0.0)
            for o in concept.objectives
        ]):
            starting_point = "All objectives are UNSTARTED — begin with framing and intuition before any assessment."
        elif mastered and not learning and not unstarted:
            starting_point = "All objectives are MASTERED — plan should be a brief synthesis or bridge to the next concept."
        elif mastered:
            starting_point = (
                f"The learner has partial knowledge. Skip basics for MASTERED objectives. "
                f"Start from the learner's current gap: focus steps on LEARNING and UNSTARTED objectives."
            )
        else:
            starting_point = "The learner is working through these objectives — start from their current level, not from scratch."

        return (
            "<task>\n"
            "Design a compact lesson sequence for a single tutoring session.\n"
            "The plan must be personalized to where this learner currently is — not a generic outline.\n"
            "</task>\n\n"
            f"<learner>\n"
            f"goal: {learner.goal}\n"
            f"teaching_style: {learner.learning_style.teaching_style}\n"
            f"verbosity: {learner.learning_style.verbosity}\n"
            f"prefers_examples: {learner.learning_style.prefers_examples}\n"
            f"</learner>\n\n"
            f"{learner_state_block}\n"
            f"<concept>\n"
            f"slug: {concept.slug}\n"
            f"title: {concept.title}\n"
            f"description: {concept.description}\n"
            f"</concept>\n\n"
            f"<objectives>\n{objectives_block}\n</objectives>\n\n"
            f"<available_content>\n{snippet_summaries}\n</available_content>\n\n"
            "<requirements>\n"
            f"- Starting point: {starting_point}\n"
            "- Use 3 to 6 steps.\n"
            "- MASTERED objectives: omit full explain steps — at most one brief diagnostic to confirm.\n"
            "- LEARNING objectives: include explain + diagnostic or practice steps.\n"
            "- UNSTARTED objectives: include a proper introductory step before any assessment.\n"
            "- Weight the plan toward the objectives with the lowest mastery.\n"
            "- Include at least one practice-oriented step for any objective that is not MASTERED.\n"
            "- End with a transition, synthesis, or next-step move.\n"
            "- Step titles should read naturally in a course sidebar.\n"
            "- Instructions should tell the tutor exactly what to do in that step.\n"
            "- Rationales should explain why that step exists pedagogically.\n"
            "</requirements>"
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

        cfg = self.config
        should_complete = False
        if action == "advance" or topic_ready_to_advance:
            should_complete = True
        elif (
            current_step.objective_id
            and current_step.objective_id == focus_objective_id
            and correctness >= cfg.step_complete_objective_threshold
        ):
            should_complete = True
        elif current_step.step_type in {"diagnostic", "practice", "review"} and correctness >= cfg.step_complete_generic_threshold:
            should_complete = True
        elif current_step.step_type == "explain" and correctness >= cfg.step_complete_explain_threshold:
            should_complete = True

        if should_complete and current_step.id not in lesson_plan.completed_step_ids:
            lesson_plan.completed_step_ids.append(current_step.id)

        while current_index < len(lesson_plan.steps) and lesson_plan.steps[current_index].id in lesson_plan.completed_step_ids:
            current_index += 1

        lesson_plan.current_step_index = min(current_index, len(lesson_plan.steps) - 1)
        lesson_plan.updated_at = datetime.now(UTC)
        return self.lesson_plan_repository.save(lesson_plan)


def _objective_status(mastery: float, threshold: float) -> str:
    if mastery >= threshold:
        return "MASTERED"
    if mastery > 0.1:
        return "LEARNING"
    return "UNSTARTED"


def _topic_mastery_label(mastery: float) -> str:
    if mastery >= 0.8:
        return "strong"
    if mastery >= 0.5:
        return "developing"
    if mastery >= 0.2:
        return "early"
    return "none yet"
