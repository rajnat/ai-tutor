from __future__ import annotations

from datetime import UTC, datetime

from app.models.domain import ConceptObjective, ObjectiveState


def utc_now() -> datetime:
    return datetime.now(UTC)


class ObjectiveGenerator:
    DEFAULT_SUFFIXES = [
        ("intuition", "Conceptual intuition"),
        ("notation", "Notation and vocabulary"),
        ("application", "Basic application"),
        ("transfer", "Transfer and explanation"),
    ]

    def infer_objectives(
        self,
        concept_slug: str,
        concept_description: str,
        objective_titles: list[str] | None = None,
    ) -> list[ConceptObjective]:
        if objective_titles:
            return [
                ConceptObjective(
                    slug=f"{concept_slug}:{self._slugify(title)}",
                    title=title,
                    description=f"Develop mastery of {title.lower()} for {concept_slug}.",
                )
                for title in objective_titles
            ]

        return [
            ConceptObjective(
                slug=f"{concept_slug}:{suffix}",
                title=title,
                description=f"{title} for {concept_slug}. {concept_description}",
            )
            for suffix, title in self.DEFAULT_SUFFIXES
        ]

    def ensure_states(
        self,
        existing: dict[str, ObjectiveState],
        objective_ids: list[str],
    ) -> dict[str, ObjectiveState]:
        for objective_id in objective_ids:
            existing.setdefault(objective_id, ObjectiveState())
        return existing

    def update_objective_states(
        self,
        objective_states: dict[str, ObjectiveState],
        objective_ids: list[str],
        correctness: float,
        confidence: float,
        scale: float = 1.0,
    ) -> dict[str, ObjectiveState]:
        now = utc_now()
        for objective_id in objective_ids:
            state = objective_states.setdefault(objective_id, ObjectiveState())
            state.mastery = min(1.0, max(0.0, state.mastery + (((correctness - 0.3) * 0.2) * scale)))
            state.confidence = min(
                1.0,
                max(0.0, (state.confidence * (1 - (0.4 * scale))) + (confidence * (0.4 * scale))),
            )
            state.last_practiced_at = now
        return objective_states

    def update_single_objective_state(
        self,
        objective_states: dict[str, ObjectiveState],
        objective_id: str,
        correctness: float,
        confidence: float,
    ) -> dict[str, ObjectiveState]:
        return self.update_objective_states(
            objective_states=objective_states,
            objective_ids=[objective_id],
            correctness=correctness,
            confidence=confidence,
            scale=1.0,
        )

    def _slugify(self, value: str) -> str:
        return "-".join(value.lower().split())
