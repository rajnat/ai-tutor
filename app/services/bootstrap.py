from __future__ import annotations

from app.models.domain import Concept
from app.services.objectives import ObjectiveGenerator
from app.services.repositories import CurriculumRepository


STARTER_CURRICULUM = [
    {
        "slug": "algebra",
        "title": "Algebra Foundations",
        "description": "Core algebraic manipulation and symbolic reasoning.",
        "subject": "math",
        "prerequisites": [],
    },
    {
        "slug": "derivatives",
        "title": "Derivatives",
        "description": "Rates of change and how functions vary.",
        "subject": "math",
        "prerequisites": ["algebra"],
    },
    {
        "slug": "russian-literature",
        "title": "Russian Literature",
        "description": "Themes, historical context, and close reading in Russian literature.",
        "subject": "literature",
        "prerequisites": [],
    },
]


def ensure_starter_curriculum(curriculum_repository: CurriculumRepository) -> None:
    objective_generator = ObjectiveGenerator()
    for concept_data in STARTER_CURRICULUM:
        if curriculum_repository.get_by_slug(concept_data["slug"]) is not None:
            continue
        curriculum_repository.create_concept(
            Concept(
                slug=concept_data["slug"],
                title=concept_data["title"],
                description=concept_data["description"],
                subject=concept_data["subject"],
                prerequisites=list(concept_data["prerequisites"]),
                objectives=objective_generator.infer_objectives(
                    concept_slug=concept_data["slug"],
                    concept_description=concept_data["description"],
                ),
            )
        )
