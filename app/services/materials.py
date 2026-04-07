from __future__ import annotations

from app.models.domain import Concept, ConceptObjective, SupplementalMaterial
from app.services.content_library import ContentLibraryService


class SupplementalMaterialService:
    def __init__(self, content_library: ContentLibraryService) -> None:
        self.content_library = content_library

    def suggest(
        self,
        topic: str,
        concept: Concept | None,
        focus_objective: ConceptObjective | None,
    ) -> list[SupplementalMaterial]:
        subject = concept.subject if concept is not None else "general"
        objective_hint = focus_objective.title if focus_objective is not None else f"{topic} fundamentals"
        retrieved = [
            SupplementalMaterial(
                title=item.title,
                material_type=_map_content_type(item.content_type),
                description=item.summary,
                rationale=(
                    f"Retrieved from the curated library for {topic} with emphasis on {objective_hint.lower()}."
                ),
                query=f"{item.source_name} | {item.content_type} | {item.difficulty}",
            )
            for item in self.content_library.retrieve(topic, focus_objective, limit=3)
        ]

        fallback_suggestions = [
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
            fallback_suggestions.append(
                SupplementalMaterial(
                    title=f"Primary Text Comparison for {topic}",
                    material_type="comparison",
                    description="Read two short primary texts or excerpts and compare theme, voice, and context.",
                    rationale="For literature topics, primary texts usually teach better than summaries alone.",
                    query=f"{topic} primary text excerpts comparison",
                )
            )

        combined: list[SupplementalMaterial] = []
        seen_titles: set[str] = set()
        for item in [*retrieved, *fallback_suggestions]:
            if item.title in seen_titles:
                continue
            combined.append(item)
            seen_titles.add(item.title)

        return combined


def _map_content_type(content_type: str) -> str:
    mapping = {
        "overview": "reading",
        "worked_example": "exercise",
        "exercise": "exercise",
        "historical_context": "reading",
        "primary_text": "reading",
        "comparison": "comparison",
        "reflection": "reflection",
    }
    return mapping.get(content_type, "reading")
