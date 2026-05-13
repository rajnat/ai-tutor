from app.models.domain import Learner, Misconception, TopicState
from app.services.tutor_config import DEFAULT_CONFIG, TutorConfig


class LearnerModelService:
    def __init__(self, config: TutorConfig = DEFAULT_CONFIG) -> None:
        self.config = config

    def ensure_topic(self, learner: Learner, topic: str) -> TopicState:
        if topic not in learner.skills:
            learner.skills[topic] = TopicState(
                mastery=self.config.initial_topic_mastery,
                confidence=self.config.initial_topic_confidence,
            )
        return learner.skills[topic]

    def update_after_evaluation(
        self,
        learner: Learner,
        topic: str,
        correctness: float,
        confidence: float,
        misconception_description: str | None,
    ) -> Learner:
        cfg = self.config
        topic_state = self.ensure_topic(learner, topic)
        topic_state.mastery = min(
            1.0,
            max(0.0, topic_state.mastery + ((correctness - cfg.mastery_neutral_correctness) * cfg.mastery_update_scale)),
        )
        retain = 1.0 - cfg.confidence_blend_factor
        topic_state.confidence = min(
            1.0,
            max(0.0, (topic_state.confidence * retain) + (confidence * cfg.confidence_blend_factor)),
        )

        if misconception_description:
            learner.misconceptions.append(
                Misconception(
                    topic=topic,
                    description=misconception_description,
                    severity=max(cfg.misconception_severity_floor, 1.0 - correctness),
                )
            )

        return learner
