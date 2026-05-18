from __future__ import annotations

from app.models.domain import Learner, ObjectiveProgress, TopicProgress
from app.services.curriculum import CurriculumPlanner
from app.services.repositories import CurriculumRepository


class ProgressService:
    def __init__(self, curriculum_repository: CurriculumRepository, curriculum_planner: CurriculumPlanner) -> None:
        self.curriculum_repository = curriculum_repository
        self.curriculum_planner = curriculum_planner

    def learner_topic_progress(self, learner: Learner, subject: str | None = None) -> list[TopicProgress]:
        concepts = self.curriculum_repository.list_concepts(subject=subject)
        progress: list[TopicProgress] = []
        for concept in concepts:
            if not any(obj.id in learner.objective_states for obj in concept.objectives):
                continue
            objective_progress = []
            for objective in concept.objectives:
                state = learner.objective_states.get(objective.id)
                mastery = state.mastery if state is not None else 0.0
                confidence = state.confidence if state is not None else 0.0
                last_practiced_at = state.last_practiced_at if state is not None else None
                objective_progress.append(
                    ObjectiveProgress(
                        objective=objective,
                        mastery=mastery,
                        confidence=confidence,
                        last_practiced_at=last_practiced_at,
                        is_ready=mastery >= objective.mastery_threshold,
                    )
                )

            topic_state = learner.skills.get(concept.slug)
            progress.append(
                TopicProgress(
                    concept=concept,
                    objectives=objective_progress,
                    concept_mastery=topic_state.mastery if topic_state is not None else 0.0,
                    concept_confidence=topic_state.confidence if topic_state is not None else 0.0,
                    ready_to_advance=self.curriculum_planner.concept_ready_to_advance(learner, concept),
                )
            )
        return progress
