from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.domain import (
    CheckpointOption,
    Concept,
    ConceptObjective,
    GenerationTrace,
    Learner,
    LessonCheckpoint,
    LessonContentBlock,
    LessonPlan,
    LessonPlanStep,
    LessonSectionContent,
    Misconception,
)
from app.services.llm import LlmProvider


class LessonContentCheckpointPayload(BaseModel):
    prompt: str
    objective_id: str | None = None
    objective_slug: str | None = None
    options: list[str] = Field(min_length=3, max_length=4)
    correct_option_index: int = Field(ge=0, le=3)
    explanation: str


class LessonContentBlockPayload(BaseModel):
    type: str = Field(pattern="^(heading|paragraph|example|checkpoint_mcq|summary|go_deeper)$")
    text: str | None = None
    prompts: list[str] = Field(default_factory=list)
    checkpoint: LessonContentCheckpointPayload | None = None


class LessonContentPayload(BaseModel):
    title: str
    subtitle: str | None = None
    blocks: list[LessonContentBlockPayload] = Field(min_length=4, max_length=8)


def _objective_status(mastery: float, threshold: float) -> str:
    if mastery >= threshold:
        return "MASTERED"
    if mastery > 0.1:
        return "LEARNING"
    return "UNSTARTED"


def _depth_guidance(mastery: float, threshold: float) -> str:
    if mastery >= threshold:
        return "The learner has mastered this objective — use a concise review framing, skip basics."
    if mastery > 0.1:
        return "The learner has partial understanding — build on what they know, address the remaining gap."
    return "The learner is new to this objective — introduce from first principles with concrete examples."


def _checkpoint_guidance(mastery: float, threshold: float) -> str:
    if mastery >= threshold:
        return "Ask a nuanced question that probes deeper understanding or edge cases."
    if mastery > 0.1:
        return "Ask an intermediate question that tests whether the core concept is solid."
    return "Ask a foundational question that reveals whether the learner grasped the basic idea."


class LessonContentService:
    PROMPT_VERSION = "lesson_content_v4"

    def __init__(self, llm_provider: LlmProvider) -> None:
        self.llm_provider = llm_provider

    def generate(
        self,
        *,
        learner: Learner,
        concept: Concept,
        lesson_plan: LessonPlan,
        active_step: LessonPlanStep | None,
        recent_messages: list[str],
        prior_wrong_answer: str | None = None,
        prior_checkpoint_explanation: str | None = None,
    ) -> LessonSectionContent:
        prompt_inputs = {
            "learner_id": learner.id,
            "concept_id": concept.id,
            "lesson_plan_id": lesson_plan.id,
            "active_step_id": active_step.id if active_step is not None else None,
            "is_remediation": prior_wrong_answer is not None,
        }
        prompt = self._build_prompt(
            learner=learner,
            concept=concept,
            lesson_plan=lesson_plan,
            active_step=active_step,
            recent_messages=recent_messages,
            prior_wrong_answer=prior_wrong_answer,
            prior_checkpoint_explanation=prior_checkpoint_explanation,
        )
        instructions = (
            "You are writing a polished lesson section for a course workspace.\n"
            "Return only JSON matching the schema.\n"
            "Optimize for clarity, pedagogical flow, and readable educational prose.\n"
            "Do not write like a chat assistant.\n"
            "Each distractor must represent a specific, named misconception — not just a wrong number or vague variation.\n"
            "The explanation must say WHY the correct answer is right and WHY each distractor is wrong."
        )
        payload = self.llm_provider.generate_structured(
            prompt=prompt,
            schema=LessonContentPayload,
            schema_name="lesson_content",
            instructions=instructions,
        )
        trace = GenerationTrace(
            provider=self.llm_provider.provider_name,
            model=self.llm_provider.model_name,
            prompt_version=self.PROMPT_VERSION,
            prompt_inputs=prompt_inputs,
        )
        return LessonSectionContent(
            title=payload.title,
            subtitle=payload.subtitle,
            blocks=[self._to_block(block, concept.objectives) for block in payload.blocks],
            trace=trace,
        )

    def _build_prompt(
        self,
        *,
        learner: Learner,
        concept: Concept,
        lesson_plan: LessonPlan,
        active_step: LessonPlanStep | None,
        recent_messages: list[str],
        prior_wrong_answer: str | None = None,
        prior_checkpoint_explanation: str | None = None,
    ) -> str:
        steps = "\n".join(f"- {step.title}: {step.instruction}" for step in lesson_plan.steps) or "- none"
        recent = "\n".join(f"- {message}" for message in recent_messages[-3:]) or "- none"

        # Objectives with inline mastery state.
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
        objectives_block = "\n".join(objective_lines) or "- none"

        # Active step's objective — the primary focus of this section.
        active_obj_id = active_step.objective_id if active_step is not None else None
        active_obj = next(
            (obj for obj in concept.objectives if obj.id == active_obj_id),
            None,
        ) if active_obj_id else None
        if active_obj is not None:
            active_obj_state = learner.objective_states.get(active_obj.id)
            active_obj_mastery = active_obj_state.mastery if active_obj_state is not None else 0.0
            active_obj_status = _objective_status(active_obj_mastery, active_obj.mastery_threshold)
            active_obj_block = (
                f"<active_objective>\n"
                f"title: {active_obj.title}\n"
                f"mastery: {active_obj_mastery:.2f} / threshold {active_obj.mastery_threshold:.2f} ({active_obj_status})\n"
                f"</active_objective>\n"
            )
            depth_guidance = _depth_guidance(active_obj_mastery, active_obj.mastery_threshold)
            checkpoint_guidance = _checkpoint_guidance(active_obj_mastery, active_obj.mastery_threshold)
        else:
            active_obj_block = ""
            depth_guidance = "Introduce the concept from first principles."
            checkpoint_guidance = "Ask a foundational question that reveals basic understanding."

        # Topic-specific misconceptions for distractor targeting.
        topic_misconceptions: list[Misconception] = [
            m for m in learner.misconceptions if m.topic == concept.slug
        ]
        misconception_block = (
            "\n".join(f"- {m.description}" for m in topic_misconceptions[-4:])
            if topic_misconceptions
            else "- none detected yet"
        )

        remediation_block = ""
        if prior_wrong_answer is not None:
            remediation_block = (
                "\n<remediation_context>\n"
                f"The learner just answered the checkpoint incorrectly.\n"
                f"What they selected: {prior_wrong_answer}\n"
                f"Why it was wrong: {prior_checkpoint_explanation or 'see explanation above'}\n"
                "Instructions:\n"
                "- Open with a brief, direct acknowledgement that the concept needs another look.\n"
                "- Reteach the idea from a different angle — use a new example or analogy.\n"
                "- Write a NEW checkpoint question that tests the same objective differently.\n"
                "- Make one distractor reflect the exact misunderstanding shown above.\n"
                "</remediation_context>\n"
            )

        mcq_guidance = (
            "MCQ checkpoint requirements:\n"
            f"- {checkpoint_guidance}\n"
            "- Each distractor must represent a specific named misconception, not just a wrong value.\n"
            "- The explanation must address why the correct answer is right AND why each distractor fails.\n"
        )
        if topic_misconceptions:
            mcq_guidance += (
                "- The learner has shown these specific misconceptions — use them as distractor material:\n"
                + "\n".join(f"  • {m.description}" for m in topic_misconceptions[-3:])
                + "\n"
            )

        return (
            "<task>\n"
            "Create one structured course section for a learner-facing lesson workspace.\n"
            "The output should read like polished educational content, not chat dialogue.\n"
            "Calibrate depth, example complexity, and checkpoint difficulty to the learner's current mastery.\n"
            f"{'This is a remediation pass — the learner got the previous checkpoint wrong.' if prior_wrong_answer else ''}\n"
            "</task>\n\n"
            f"<learner>\n"
            f"goal: {learner.goal}\n"
            f"teaching_style: {learner.learning_style.teaching_style}\n"
            f"verbosity: {learner.learning_style.verbosity}\n"
            f"prefers_examples: {learner.learning_style.prefers_examples}\n"
            f"</learner>\n\n"
            f"<learner_misconceptions>\n{misconception_block}\n</learner_misconceptions>\n\n"
            f"<concept>\n"
            f"title: {concept.title}\n"
            f"description: {concept.description}\n"
            f"</concept>\n\n"
            f"<active_step>\n"
            f"title: {active_step.title if active_step is not None else 'Start lesson'}\n"
            f"instruction: {active_step.instruction if active_step is not None else 'Introduce the topic'}\n"
            f"</active_step>\n\n"
            f"{active_obj_block}"
            f"<objectives>\n{objectives_block}\n</objectives>\n\n"
            f"<lesson_steps>\n{steps}\n</lesson_steps>\n\n"
            f"<recent_context>\n{recent}\n</recent_context>\n"
            f"{remediation_block}\n"
            "<requirements>\n"
            "- Use 4 to 8 blocks.\n"
            "- Include exactly one checkpoint_mcq block.\n"
            f"- Content depth: {depth_guidance}\n"
            "- Start with a strong conceptual opening before the checkpoint.\n"
            "- Use prose that would look good in a course reader.\n"
            "- The example should make the concept more concrete, not repeat the definition.\n"
            f"- {mcq_guidance}"
            "- End with a short summary or forward-looking close.\n"
            "</requirements>"
        )

    def _to_block(
        self,
        payload: LessonContentBlockPayload,
        objectives: list[ConceptObjective],
    ) -> LessonContentBlock:
        checkpoint = None
        if payload.checkpoint is not None:
            checkpoint = LessonCheckpoint(
                prompt=payload.checkpoint.prompt,
                objective_id=payload.checkpoint.objective_id,
                objective_slug=payload.checkpoint.objective_slug,
                options=[
                    CheckpointOption(
                        id=f"option-{index}",
                        label=chr(ord("A") + index),
                        text=option_text,
                    )
                    for index, option_text in enumerate(payload.checkpoint.options)
                ],
                correct_option_id=f"option-{payload.checkpoint.correct_option_index}",
                explanation=payload.checkpoint.explanation,
            )
            if checkpoint.objective_id is None and checkpoint.objective_slug is not None:
                matched = next((objective for objective in objectives if objective.slug == checkpoint.objective_slug), None)
                checkpoint.objective_id = matched.id if matched is not None else None
        return LessonContentBlock(
            type=payload.type,
            text=payload.text,
            checkpoint=checkpoint,
            prompts=payload.prompts,
        )
