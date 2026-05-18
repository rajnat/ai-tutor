import re

from app.models.domain import Learner, Misconception, TopicState
from app.services.tutor_config import DEFAULT_CONFIG, TutorConfig

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "it", "in", "on", "of", "to", "and", "or",
    "but", "not", "with", "for", "as", "at", "by", "this", "that", "was",
    "are", "be", "been", "has", "have", "had", "they", "their", "them",
    "than", "so", "when", "which", "who", "what", "from", "into",
})


def _word_set(text: str) -> frozenset[str]:
    words = re.sub(r"[^a-z0-9\s]", "", text.lower()).split()
    return frozenset(w for w in words if w not in _STOP_WORDS and len(w) > 2)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_duplicate(
    description: str,
    existing: list[Misconception],
    threshold: float,
) -> bool:
    candidate_words = _word_set(description)
    return any(
        _jaccard(candidate_words, _word_set(m.description)) >= threshold
        for m in existing
    )


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

        topic_misconceptions = [m for m in learner.misconceptions if m.topic == topic]

        # Resolution: a clean correct answer (no new misconception detected) at high
        # correctness + sufficient confidence resolves the most recent topic misconception.
        # That's the one the tutor was most likely just working on.
        if (
            misconception_description is None
            and correctness >= cfg.misconception_resolution_correctness
            and confidence >= cfg.misconception_resolution_confidence
            and topic_misconceptions
        ):
            to_resolve = topic_misconceptions[-1]
            learner.misconceptions = [m for m in learner.misconceptions if m is not to_resolve]
            topic_misconceptions = [m for m in learner.misconceptions if m.topic == topic]

        # Deduplication + append: skip if a near-duplicate already exists for this topic.
        if misconception_description:
            if not _is_duplicate(misconception_description, topic_misconceptions, cfg.misconception_dedup_similarity):
                learner.misconceptions.append(
                    Misconception(
                        topic=topic,
                        description=misconception_description,
                        severity=max(cfg.misconception_severity_floor, 1.0 - correctness),
                    )
                )
                topic_misconceptions = [m for m in learner.misconceptions if m.topic == topic]

            # Enforce per-topic cap by dropping the oldest entry.
            while len(topic_misconceptions) > cfg.misconception_max_per_topic:
                oldest = topic_misconceptions[0]
                learner.misconceptions = [m for m in learner.misconceptions if m is not oldest]
                topic_misconceptions = topic_misconceptions[1:]

        return learner
