from app.models.domain import Concept, ConceptObjective, Learner, LearningPace, SessionMode, TutorAction, TutorTurn
from app.services.tutor_config import DEFAULT_CONFIG, TutorConfig


class CurriculumPlanner:
    def __init__(self, config: TutorConfig = DEFAULT_CONFIG) -> None:
        self.config = config

    def assess_learning_pace(
        self,
        recent_turns: list[TutorTurn],
        mastery: float,
    ) -> LearningPace:
        """Classify how fast the learner is progressing right now.

        Uses a rolling correctness average plus a "stuck at novice" guard for
        learners who have had many turns without mastery movement.
        """
        cfg = self.config
        window = recent_turns[-cfg.pace_recent_turns_window :]
        if not window:
            return LearningPace.NORMAL

        avg_correctness = sum(t.evaluation.correctness for t in window) / len(window)

        if len(recent_turns) >= cfg.pace_struggling_turns_minimum and mastery < cfg.mastery_novice_threshold:
            return LearningPace.STRUGGLING
        if avg_correctness < cfg.pace_struggling_avg_correctness:
            return LearningPace.STRUGGLING
        if avg_correctness >= cfg.pace_accelerating_avg_correctness:
            return LearningPace.ACCELERATING
        return LearningPace.NORMAL

    def choose_action(
        self,
        topic: str,
        mastery: float,
        mode: SessionMode,
        misconception_detected: bool,
        confidence: float = 0.5,
        recent_misconception_count: int = 0,
        learning_pace: LearningPace = LearningPace.NORMAL,
    ) -> TutorAction:
        cfg = self.config

        # Session mode overrides everything.
        if mode == SessionMode.TEST:
            return TutorAction.ASK_PRACTICE
        if mode == SessionMode.REVIEW or misconception_detected:
            return TutorAction.REINFORCE

        # Accumulated misconceptions on this topic signal persistent confusion —
        # one REINFORCE turn is not enough; keep correcting.
        if recent_misconception_count >= cfg.difficulty_high_misconception_count:
            return TutorAction.REINFORCE

        # Base action from mastery level.
        if mastery < cfg.mastery_novice_threshold:
            action = TutorAction.EXPLAIN
        elif mastery < cfg.mastery_intermediate_threshold:
            action = TutorAction.ASK_DIAGNOSTIC
        else:
            action = TutorAction.ADVANCE

        # Confidence gate: mastery may be high from lucky guesses; don't advance
        # until the learner can also answer reliably.
        if action == TutorAction.ADVANCE and confidence < cfg.difficulty_low_confidence_threshold:
            action = TutorAction.ASK_DIAGNOSTIC

        # Learning pace adjustments: demote one level when struggling so the
        # learner gets more scaffolding; promote EXPLAIN → ASK_DIAGNOSTIC when
        # accelerating so we don't waste time on content the learner has grasped.
        if learning_pace == LearningPace.STRUGGLING:
            if action == TutorAction.ADVANCE:
                action = TutorAction.ASK_DIAGNOSTIC
            elif action == TutorAction.ASK_DIAGNOSTIC:
                action = TutorAction.EXPLAIN
        elif learning_pace == LearningPace.ACCELERATING and action == TutorAction.EXPLAIN:
            action = TutorAction.ASK_DIAGNOSTIC

        return action

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
