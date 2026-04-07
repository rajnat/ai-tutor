from app.models.domain import Learner, SessionMode, TutorAction


class CurriculumPlanner:
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
        if mastery < 0.3:
            return TutorAction.EXPLAIN
        if mastery < 0.7:
            return TutorAction.ASK_DIAGNOSTIC
        return TutorAction.ADVANCE

    def suggest_next_topic(self, learner: Learner) -> str | None:
        if not learner.skills:
            return None
        weakest = min(learner.skills.items(), key=lambda item: item[1].mastery)
        return weakest[0]
