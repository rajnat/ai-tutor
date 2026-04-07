from app.models.domain import Learner, Misconception, TopicState


class LearnerModelService:
    def ensure_topic(self, learner: Learner, topic: str) -> TopicState:
        if topic not in learner.skills:
            learner.skills[topic] = TopicState(mastery=0.1, confidence=0.1)
        return learner.skills[topic]

    def update_after_evaluation(
        self,
        learner: Learner,
        topic: str,
        correctness: float,
        confidence: float,
        misconception_description: str | None,
    ) -> Learner:
        topic_state = self.ensure_topic(learner, topic)
        topic_state.mastery = min(1.0, max(0.0, topic_state.mastery + ((correctness - 0.5) * 0.2)))
        topic_state.confidence = min(1.0, max(0.0, (topic_state.confidence * 0.6) + (confidence * 0.4)))

        if misconception_description:
            learner.misconceptions.append(
                Misconception(
                    topic=topic,
                    description=misconception_description,
                    severity=max(0.3, 1.0 - correctness),
                )
            )

        return learner
