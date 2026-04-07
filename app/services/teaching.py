from __future__ import annotations

from typing import Protocol

from app.models.domain import (
    Concept,
    ConceptObjective,
    ContentSnippet,
    GenerationTrace,
    Learner,
    LearningMemoryContext,
    LessonPlan,
    SessionMode,
    TeachingResponse,
    TutorAction,
    TutorTurn,
)
from app.services.llm import LlmProvider


class Teacher(Protocol):
    def respond(
        self,
        learner: Learner,
        topic: str,
        action: TutorAction,
        learner_message: str,
        mode: SessionMode,
        current_concept: Concept | None = None,
        next_concept: Concept | None = None,
        focus_objective: ConceptObjective | None = None,
        recent_turns: list[TutorTurn] | None = None,
        memory_context: LearningMemoryContext | None = None,
        content_snippets: list[ContentSnippet] | None = None,
        lesson_plan: LessonPlan | None = None,
    ) -> TeachingResponse: ...


class OpenAITeachingService:
    _RECENT_TURN_LIMIT = 3
    PROMPT_VERSION = "teaching_v3"

    def __init__(self, llm_provider: LlmProvider) -> None:
        self.llm_provider = llm_provider

    def respond(
        self,
        learner: Learner,
        topic: str,
        action: TutorAction,
        learner_message: str,
        mode: SessionMode,
        current_concept: Concept | None = None,
        next_concept: Concept | None = None,
        focus_objective: ConceptObjective | None = None,
        recent_turns: list[TutorTurn] | None = None,
        memory_context: LearningMemoryContext | None = None,
        content_snippets: list[ContentSnippet] | None = None,
        lesson_plan: LessonPlan | None = None,
    ) -> TeachingResponse:
        prompt_inputs = {
            "topic": topic,
            "action": action.value,
            "mode": mode.value,
            "current_concept_id": current_concept.id if current_concept is not None else None,
            "next_concept_id": next_concept.id if next_concept is not None else None,
            "focus_objective_id": focus_objective.id if focus_objective is not None else None,
            "recent_turn_ids": [turn.id for turn in (recent_turns or [])[-self._RECENT_TURN_LIMIT :]],
            "memory_summary": memory_context.summary if memory_context is not None else "",
            "content_ids": [snippet.id for snippet in (content_snippets or [])],
            "lesson_plan_id": lesson_plan.id if lesson_plan is not None else None,
        }
        prompt = self._build_prompt(
            learner=learner,
            topic=topic,
            action=action,
            learner_message=learner_message,
            mode=mode,
            current_concept=current_concept,
            next_concept=next_concept,
            focus_objective=focus_objective,
            recent_turns=recent_turns or [],
            memory_context=memory_context,
            content_snippets=content_snippets or [],
            lesson_plan=lesson_plan,
        )
        instructions = (
            "You are an expert AI tutor. Be warm, concise, and pedagogically intentional. "
            "Teach the learner rather than merely answering. "
            "Use the requested tutor action exactly and adapt to the learner's teaching style preference. "
            "Socratic style means mostly one guiding question with minimal exposition. "
            "Direct style means clear explanation first, then a brief check for understanding. "
            "Blended style means short explanation plus one guiding question. "
            "Use the weak objective and recent turns to stay on the same instructional thread. "
            "Do not mention hidden system logic, scoring, or mastery numbers. "
            "Keep the response to 3-6 sentences total. "
            "If asking a question, ask exactly one focused question. "
            "If correcting the learner, be supportive, explicit about what was off, and then re-anchor with a better mental model. "
            "Prefer concrete examples when the learner prefers examples."
        )
        response = self.llm_provider.generate_text(prompt=prompt, instructions=instructions).strip()
        return TeachingResponse(
            text=response,
            trace=GenerationTrace(
                provider=self.llm_provider.provider_name,
                model=self.llm_provider.model_name,
                prompt_version=self.PROMPT_VERSION,
                prompt_inputs=prompt_inputs,
            ),
        )

    def _build_prompt(
        self,
        learner: Learner,
        topic: str,
        action: TutorAction,
        learner_message: str,
        mode: SessionMode,
        current_concept: Concept | None,
        next_concept: Concept | None,
        focus_objective: ConceptObjective | None,
        recent_turns: list[TutorTurn],
        memory_context: LearningMemoryContext | None,
        content_snippets: list[ContentSnippet],
        lesson_plan: LessonPlan | None,
    ) -> str:
        weak_objective = focus_objective.title if focus_objective is not None else "general understanding"
        weak_objective_description = (
            focus_objective.description if focus_objective is not None else "Build the learner's core understanding."
        )
        older_turns_summary = self._summarize_older_turns(recent_turns)
        detailed_recent_turns = recent_turns[-self._RECENT_TURN_LIMIT :]
        current_concept_text = (
            f"{current_concept.title}: {current_concept.description}"
            if current_concept is not None
            else topic
        )
        next_concept_text = (
            f"{next_concept.title}: {next_concept.description}"
            if next_concept is not None
            else "none"
        )
        misconceptions = (
            ", ".join(misconception.description for misconception in learner.misconceptions[-3:])
            if learner.misconceptions
            else "none"
        )
        recent_turns_text = self._format_recent_turns(detailed_recent_turns)
        style_guidance = {
            "socratic": "Keep exposition minimal and lead with one carefully chosen question.",
            "direct": "Explain clearly and explicitly before checking understanding.",
            "blended": "Mix a short explanation with one guiding question.",
        }[learner.learning_style.teaching_style]
        verbosity_guidance = {
            "low": "Keep it very concise.",
            "medium": "Use a few sentences with enough context to be helpful.",
            "high": "You may use a little more scaffolding and detail, but stay focused.",
        }[learner.learning_style.verbosity]
        mode_guidance = {
            SessionMode.LEARN: "Optimize for understanding and momentum, not assessment pressure.",
            SessionMode.ASK: "Answer the learner's question directly, then optionally add one clarifying check.",
            SessionMode.TEST: "Behave more like a coach giving a check for understanding than a lecturer.",
            SessionMode.REVIEW: "Prioritize recall, correction, and reconnection to previously weak ideas.",
        }[mode]
        exemplars_text = self._build_exemplars(
            topic=topic,
            current_concept=current_concept,
            focus_objective=focus_objective,
        )
        memory_text = self._format_memory_context(memory_context)
        content_text = self._format_content_snippets(content_snippets)
        lesson_plan_text = self._format_lesson_plan(lesson_plan)

        action_guidance = {
            TutorAction.EXPLAIN: (
                "Give a clearer explanation of the concept. Build intuition first, then ground it in a simple example, and end with one short understanding check."
            ),
            TutorAction.ASK_DIAGNOSTIC: (
                "Ask one targeted question that checks the learner's understanding of the weak objective."
            ),
            TutorAction.ASK_PRACTICE: (
                "Give one short practice prompt and ask the learner to justify their answer briefly."
            ),
            TutorAction.REINFORCE: (
                "Correct the likely misunderstanding gently, then ask one focused follow-up."
            ),
            TutorAction.ADVANCE: (
                "Acknowledge progress, connect the current concept to the next one, and smoothly transition."
            ),
        }[action]

        return (
            f"<learner>\n"
            f"name: {learner.name}\n"
            f"goal: {learner.goal}\n"
            f"teaching_style: {learner.learning_style.teaching_style}\n"
            f"prefers_examples: {learner.learning_style.prefers_examples}\n"
            f"verbosity: {learner.learning_style.verbosity}\n"
            f"recent_misconceptions: {misconceptions}\n"
            f"</learner>\n\n"
            f"<lesson>\n"
            f"mode: {mode.value}\n"
            f"topic: {topic}\n"
            f"concept_context: {current_concept_text}\n"
            f"requested_action: {action.value}\n"
            f"weak_objective: {weak_objective}\n"
            f"weak_objective_description: {weak_objective_description}\n"
            f"next_concept: {next_concept_text}\n"
            f"</lesson>\n\n"
            f"<pedagogy>\n"
            f"style_guidance: {style_guidance}\n"
            f"verbosity_guidance: {verbosity_guidance}\n"
            f"mode_guidance: {mode_guidance}\n"
            f"prefers_examples: {learner.learning_style.prefers_examples}\n"
            f"</pedagogy>\n\n"
            f"<session_summary>\n{older_turns_summary}\n</session_summary>\n\n"
            f"<recent_turns>\n{recent_turns_text}\n</recent_turns>\n\n"
            f"<teaching_context>\n{exemplars_text}\n</teaching_context>\n\n"
            f"<lesson_plan>\n{lesson_plan_text}\n</lesson_plan>\n\n"
            f"<retrieved_content>\n{content_text}\n</retrieved_content>\n\n"
            f"<learner_memory>\n{memory_text}\n</learner_memory>\n\n"
            f"<learner_message>\n{learner_message}\n</learner_message>\n\n"
            f"<teaching_goal>\n{action_guidance}\n</teaching_goal>\n\n"
            "Respond as the tutor to the learner."
        )

    def _format_recent_turns(self, recent_turns: list[TutorTurn]) -> str:
        if not recent_turns:
            return "none"

        lines: list[str] = []
        for turn in recent_turns[-3:]:
            lines.append(
                f"learner: {turn.learner_message}\n"
                f"tutor_action: {turn.tutor_action.value}\n"
                f"tutor: {turn.tutor_response}"
            )
        return "\n---\n".join(lines)

    def _summarize_older_turns(self, turns: list[TutorTurn]) -> str:
        if len(turns) <= self._RECENT_TURN_LIMIT:
            return "none"

        older_turns = turns[: -self._RECENT_TURN_LIMIT]
        action_counts: dict[str, int] = {}
        low_confidence_count = 0
        misconception_count = 0
        objectives: list[str] = []

        for turn in older_turns:
            action_key = turn.tutor_action.value
            action_counts[action_key] = action_counts.get(action_key, 0) + 1
            if turn.evaluation.confidence < 0.5:
                low_confidence_count += 1
            if turn.evaluation.misconception_detected:
                misconception_count += 1
            if turn.evaluation.objective_id and turn.evaluation.objective_id not in objectives:
                objectives.append(turn.evaluation.objective_id)

        actions_text = ", ".join(f"{name} x{count}" for name, count in sorted(action_counts.items()))
        objectives_text = ", ".join(objectives) if objectives else "none tagged"
        return (
            f"{len(older_turns)} earlier turns. "
            f"Prior tutor moves: {actions_text or 'none'}. "
            f"Low-confidence turns: {low_confidence_count}. "
            f"Misconceptions flagged: {misconception_count}. "
            f"Objectives touched: {objectives_text}."
        )

    def _build_exemplars(
        self,
        topic: str,
        current_concept: Concept | None,
        focus_objective: ConceptObjective | None,
    ) -> str:
        concept_title = current_concept.title if current_concept is not None else topic
        concept_description = current_concept.description if current_concept is not None else topic
        if focus_objective is None:
            return (
                f"Concept anchor: {concept_title}. {concept_description}\n"
                "Tutor pattern: explain the core idea plainly, then connect it to one concrete example."
            )

        objective_text = f"{focus_objective.slug} {focus_objective.title} {focus_objective.description}".lower()
        if "notation" in objective_text or "vocabulary" in objective_text:
            exemplar = (
                "Example tutoring move: define one symbol or term clearly, contrast it with a nearby confusion, "
                "then ask the learner what the symbol means in context."
            )
        elif "intuition" in objective_text or "concept" in objective_text:
            exemplar = (
                "Example tutoring move: explain the idea in plain language, tie it to an everyday mental model, "
                "then ask the learner to restate the core idea."
            )
        elif "application" in objective_text or "solve" in objective_text:
            exemplar = (
                "Example tutoring move: walk through one short worked step, then ask the learner to do the next step and justify it."
            )
        elif "transfer" in objective_text or "compare" in objective_text or "explain" in objective_text:
            exemplar = (
                "Example tutoring move: connect this idea to a nearby example or comparison, then ask the learner what changes and what stays the same."
            )
        else:
            exemplar = (
                "Example tutoring move: focus on one subskill at a time, using one concrete example and one focused follow-up question."
            )

        return (
            f"Concept anchor: {concept_title}. {concept_description}\n"
            f"Objective anchor: {focus_objective.title}. {focus_objective.description}\n"
            f"{exemplar}"
        )

    def _format_memory_context(self, memory_context: LearningMemoryContext | None) -> str:
        if memory_context is None:
            return "none"

        related_turns = "\n".join(f"- {item}" for item in memory_context.related_turns) or "- none"
        misconception_notes = "\n".join(f"- {item}" for item in memory_context.misconception_notes) or "- none"
        prior_successes = "\n".join(f"- {item}" for item in memory_context.prior_successes) or "- none"
        return (
            f"summary: {memory_context.summary}\n"
            f"misconceptions:\n{misconception_notes}\n"
            f"prior_successes:\n{prior_successes}\n"
            f"related_turns:\n{related_turns}"
        )

    def _format_content_snippets(self, content_snippets: list[ContentSnippet]) -> str:
        if not content_snippets:
            return "none"

        formatted: list[str] = []
        for snippet in content_snippets[:3]:
            excerpt = " ".join(snippet.text.split())[:320]
            formatted.append(
                f"title: {snippet.title}\n"
                f"type: {snippet.content_type}\n"
                f"summary: {snippet.summary}\n"
                f"source: {snippet.source_name}\n"
                f"excerpt: {excerpt}"
            )
        return "\n---\n".join(formatted)

    def _format_lesson_plan(self, lesson_plan: LessonPlan | None) -> str:
        if lesson_plan is None:
            return "none"
        steps = "\n".join(
            f"- {step.step_type}: {step.title} | objective={step.objective_slug or step.objective_id or 'none'} | instruction={step.instruction}"
            for step in lesson_plan.steps
        ) or "- none"
        return f"summary: {lesson_plan.summary}\nsteps:\n{steps}"
