from app.models.domain import Concept, ConceptObjective, Learner, SessionMode, TutorAction
from app.services.tutor_config import DEFAULT_CONFIG, TutorConfig


class CurriculumPlanner:
    def __init__(self, config: TutorConfig = DEFAULT_CONFIG) -> None:
        self.config = config

    def choose_action(
        self,
        topic: str,
        mastery: float,
        mode: SessionMode,
        misconception_detected: bool,
    ) -> TutorAction:
        if mode == SessionMode.TEST:
            return TutorAction.ASK_PRACTICE
        if mode == SessionMode.REVIEW or misconception_detected:
            return TutorAction.REINFORCE
        if mastery < self.config.mastery_novice_threshold:
            return TutorAction.EXPLAIN
        if mastery < self.config.mastery_intermediate_threshold:
            return TutorAction.ASK_DIAGNOSTIC
        return TutorAction.ADVANCE

    def suggest_next_topic(self, learner: Learner, concepts: list[Concept]) -> list[Concept]:
        if not concepts:
            return []

        ready_concepts: list[tuple[float, Concept]] = []
        for concept in concepts:
            if concept.slug in learner.skills and learner.skills[concept.slug].mastery >= self.config.mastery_complete_threshold:
                continue

            prereqs_met = all(
                learner.skills.get(prereq) is not None
                and learner.skills[prereq].mastery >= self.config.prerequisite_mastery_threshold
                for prereq in concept.prerequisites
            )
            if not prereqs_met and concept.prerequisites:
                continue

            concept_mastery = learner.skills.get(concept.slug).mastery if concept.slug in learner.skills else 0.0
            ready_concepts.append((concept_mastery, concept))

        ready_concepts.sort(key=lambda item: item[0])
        return [concept for _, concept in ready_concepts]

    def choose_next_concept(self, current_topic: str, learner: Learner, concepts: list[Concept]) -> Concept | None:
        recommendations = self.suggest_next_topic(learner, concepts)
        for concept in recommendations:
            if concept.slug != current_topic:
                return concept
        return None

    def concept_ready_to_advance(self, learner: Learner, concept: Concept | None) -> bool:
        if concept is None:
            return False
        if not concept.objectives:
            state = learner.skills.get(concept.slug)
            return state is not None and state.mastery >= self.config.mastery_complete_threshold

        for objective in concept.objectives:
            state = learner.objective_states.get(objective.id)
            if state is None or state.mastery < objective.mastery_threshold:
                return False
        return True

    def weakest_objective(self, learner: Learner, concept: Concept | None) -> ConceptObjective | None:
        if concept is None or not concept.objectives:
            return None

        weakest: tuple[float, ConceptObjective] | None = None
        for objective in concept.objectives:
            state = learner.objective_states.get(objective.id)
            mastery = state.mastery if state is not None else 0.0
            if weakest is None or mastery < weakest[0]:
                weakest = (mastery, objective)
        return weakest[1] if weakest is not None else None
