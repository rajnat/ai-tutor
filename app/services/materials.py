from __future__ import annotations

from app.models.domain import Concept, ConceptObjective, SupplementalMaterial


class SupplementalMaterialService:
    def suggest(
        self,
        topic: str,
        concept: Concept | None,
        focus_objective: ConceptObjective | None,
    ) -> list[SupplementalMaterial]:
        subject = concept.subject if concept is not None else "general"
        objective_hint = focus_objective.title if focus_objective is not None else f"{topic} fundamentals"

        suggestions = [
            SupplementalMaterial(
                title=f"Foundational Reading on {topic}",
                material_type="reading",
                description=f"Read a concise overview focused on {objective_hint.lower()}.",
                rationale=f"A short reading can reinforce the weakest area: {objective_hint.lower()}.",
                query=f"{subject} {topic} beginner reading {objective_hint}",
            ),
            SupplementalMaterial(
                title=f"Worked Examples for {topic}",
                material_type="exercise",
                description=f"Study and redo a few worked examples centered on {objective_hint.lower()}.",
                rationale="Examples help convert passive understanding into usable skill.",
                query=f"{subject} {topic} worked examples {objective_hint}",
            ),
            SupplementalMaterial(
                title=f"Reflective Prompt on {topic}",
                material_type="reflection",
                description=f"Write a short explanation of {topic} in your own words with emphasis on {objective_hint.lower()}.",
                rationale="Self-explanation is a strong way to reveal and repair gaps.",
                query=f"{subject} {topic} self explanation prompt {objective_hint}",
            ),
        ]

        if subject.lower() in {"literature", "russian literature", "history", "humanities"} or "literature" in topic.lower():
            suggestions.append(
                SupplementalMaterial(
                    title=f"Primary Text Comparison for {topic}",
                    material_type="comparison",
                    description="Read two short primary texts or excerpts and compare theme, voice, and context.",
                    rationale="For literature topics, primary texts usually teach better than summaries alone.",
                    query=f"{topic} primary text excerpts comparison",
                )
            )

        return suggestions
