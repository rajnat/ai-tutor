from __future__ import annotations

from app.models.domain import ConceptObjective, Learner, LearningMemoryContext, Session, TutorTurn
from app.services.repositories import SessionRepository


class LearningMemoryService:
    def __init__(self, session_repository: SessionRepository) -> None:
        self.session_repository = session_repository

    def build_context(
        self,
        learner: Learner,
        topic: str,
        focus_objective: ConceptObjective | None,
        current_session: Session,
    ) -> LearningMemoryContext:
        sessions = self.session_repository.list_for_learner(learner.id, limit=8)
        relevant_turns: list[TutorTurn] = []
        for session in sessions:
            for turn in session.turns:
                if session.id == current_session.id and turn.id in {current_turn.id for current_turn in current_session.turns}:
                    continue
                if session.topic == topic:
                    relevant_turns.append(turn)
                    continue
                if (
                    focus_objective is not None
                    and turn.evaluation.objective_id == focus_objective.id
                ):
                    relevant_turns.append(turn)

        misconception_notes = [
            misconception.description
            for misconception in learner.misconceptions
            if misconception.topic == topic
        ][-3:]

        prior_successes = [
            turn.learner_message
            for turn in relevant_turns
            if turn.evaluation.correctness >= 0.7
        ][-2:]

        related_turn_notes = []
        for turn in relevant_turns[-3:]:
            note = (
                f"Learner said: {turn.learner_message} | "
                f"Tutor responded: {turn.tutor_response}"
            )
            related_turn_notes.append(note)

        summary_parts = []
        if focus_objective is not None:
            summary_parts.append(f"Current weak objective: {focus_objective.title}.")
        if misconception_notes:
            summary_parts.append(f"Recent misconceptions on this topic: {len(misconception_notes)}.")
        if prior_successes:
            summary_parts.append("The learner has shown partial success on related ideas before.")
        if not summary_parts:
            summary_parts.append("Little prior memory exists for this topic yet.")

        return LearningMemoryContext(
            summary=" ".join(summary_parts),
            related_turns=related_turn_notes,
            misconception_notes=misconception_notes,
            prior_successes=prior_successes,
        )
