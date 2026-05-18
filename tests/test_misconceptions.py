"""Tests for misconception deduplication and resolution in LearnerModelService."""
from app.models.domain import Learner, LearningPreferences, Misconception
from app.services.learner_model import LearnerModelService, _is_duplicate, _word_set
from app.services.tutor_config import TutorConfig


def _learner(*descriptions: tuple[str, str]) -> Learner:
    """Build a learner with pre-seeded misconceptions. Each tuple is (topic, description)."""
    misconceptions = [
        Misconception(topic=topic, description=desc, severity=0.6)
        for topic, desc in descriptions
    ]
    return Learner(
        name="Test",
        goal="Learn",
        learning_style=LearningPreferences(),
        misconceptions=misconceptions,
    )


def _cfg(**overrides) -> TutorConfig:
    return TutorConfig(**overrides)


# ---------------------------------------------------------------------------
# _word_set and _is_duplicate unit tests
# ---------------------------------------------------------------------------

class TestWordSet:
    def test_strips_stop_words(self) -> None:
        words = _word_set("a confused and lost learner")
        assert "a" not in words
        assert "and" not in words
        assert "confused" in words
        assert "lost" in words

    def test_lowercases(self) -> None:
        assert _word_set("Derivative") == _word_set("derivative")

    def test_strips_punctuation(self) -> None:
        assert "derivative" in _word_set("derivative, integral.")

    def test_empty_string_returns_empty_set(self) -> None:
        assert _word_set("") == frozenset()


class TestIsDuplicate:
    def test_near_identical_is_duplicate(self) -> None:
        existing = [Misconception(topic="calc", description="confused derivative with integral", severity=0.5)]
        assert _is_duplicate("confused derivative with integral again", existing, threshold=0.4)

    def test_completely_different_is_not_duplicate(self) -> None:
        existing = [Misconception(topic="calc", description="confused derivative with integral", severity=0.5)]
        assert not _is_duplicate("thought sine function was linear", existing, threshold=0.4)

    def test_empty_existing_is_never_duplicate(self) -> None:
        assert not _is_duplicate("any description", [], threshold=0.4)

    def test_threshold_boundary(self) -> None:
        # "rate change" vs "rate change speed" — 2/3 overlap = 0.67, above 0.4
        existing = [Misconception(topic="t", description="rate change", severity=0.5)]
        assert _is_duplicate("rate change speed", existing, threshold=0.4)
        # but NOT above 0.8
        assert not _is_duplicate("rate change speed", existing, threshold=0.8)


# ---------------------------------------------------------------------------
# LearnerModelService.update_after_evaluation — misconception lifecycle
# ---------------------------------------------------------------------------

class TestMisconceptionDeduplication:
    def test_new_misconception_added_when_no_duplicates(self) -> None:
        svc = LearnerModelService()
        learner = _learner()
        result = svc.update_after_evaluation(
            learner=learner,
            topic="calculus",
            correctness=0.2,
            confidence=0.3,
            misconception_description="thinks derivative measures area under curve",
        )
        topic_miscs = [m for m in result.misconceptions if m.topic == "calculus"]
        assert len(topic_miscs) == 1

    def test_near_duplicate_is_not_added(self) -> None:
        svc = LearnerModelService()
        learner = _learner(("calculus", "confused derivative with integral measures area"))
        result = svc.update_after_evaluation(
            learner=learner,
            topic="calculus",
            correctness=0.2,
            confidence=0.3,
            misconception_description="derivative confused with integral area measures",
        )
        topic_miscs = [m for m in result.misconceptions if m.topic == "calculus"]
        assert len(topic_miscs) == 1  # not added

    def test_distinct_misconception_is_added_alongside_existing(self) -> None:
        svc = LearnerModelService()
        learner = _learner(("calculus", "confused derivative with integral"))
        result = svc.update_after_evaluation(
            learner=learner,
            topic="calculus",
            correctness=0.2,
            confidence=0.3,
            misconception_description="thinks chain rule applies to addition",
        )
        topic_miscs = [m for m in result.misconceptions if m.topic == "calculus"]
        assert len(topic_miscs) == 2

    def test_misconceptions_from_other_topics_not_affected(self) -> None:
        svc = LearnerModelService()
        learner = _learner(("algebra", "confused variable with constant"))
        result = svc.update_after_evaluation(
            learner=learner,
            topic="calculus",
            correctness=0.2,
            confidence=0.3,
            misconception_description="derivative means area",
        )
        assert len([m for m in result.misconceptions if m.topic == "algebra"]) == 1
        assert len([m for m in result.misconceptions if m.topic == "calculus"]) == 1


class TestMisconceptionCap:
    def test_oldest_dropped_when_cap_exceeded(self) -> None:
        cfg = _cfg(misconception_max_per_topic=3)
        svc = LearnerModelService(config=cfg)
        learner = _learner(
            ("calc", "misconception alpha"),
            ("calc", "misconception beta"),
            ("calc", "misconception gamma"),
        )
        result = svc.update_after_evaluation(
            learner=learner,
            topic="calc",
            correctness=0.1,
            confidence=0.2,
            misconception_description="misconception delta",
        )
        topic_miscs = [m for m in result.misconceptions if m.topic == "calc"]
        assert len(topic_miscs) == 3
        descriptions = [m.description for m in topic_miscs]
        assert "misconception alpha" not in descriptions  # oldest dropped
        assert "misconception delta" in descriptions

    def test_cap_not_exceeded_when_duplicate_skipped(self) -> None:
        cfg = _cfg(misconception_max_per_topic=3)
        svc = LearnerModelService(config=cfg)
        learner = _learner(
            ("calc", "misconception alpha"),
            ("calc", "misconception beta"),
            ("calc", "misconception gamma"),
        )
        # This is a near-duplicate of alpha — should be skipped, cap not triggered
        result = svc.update_after_evaluation(
            learner=learner,
            topic="calc",
            correctness=0.1,
            confidence=0.2,
            misconception_description="misconception alpha duplicate",
        )
        topic_miscs = [m for m in result.misconceptions if m.topic == "calc"]
        assert len(topic_miscs) == 3
        assert "misconception alpha" in [m.description for m in topic_miscs]


class TestMisconceptionResolution:
    def test_high_correctness_resolves_most_recent_topic_misconception(self) -> None:
        cfg = _cfg(
            misconception_resolution_correctness=0.8,
            misconception_resolution_confidence=0.5,
        )
        svc = LearnerModelService(config=cfg)
        learner = _learner(
            ("calc", "older misconception"),
            ("calc", "newer misconception"),
        )
        result = svc.update_after_evaluation(
            learner=learner,
            topic="calc",
            correctness=0.9,
            confidence=0.7,
            misconception_description=None,
        )
        topic_miscs = [m for m in result.misconceptions if m.topic == "calc"]
        assert len(topic_miscs) == 1
        assert topic_miscs[0].description == "older misconception"  # newest was resolved

    def test_resolution_does_not_fire_below_correctness_threshold(self) -> None:
        cfg = _cfg(misconception_resolution_correctness=0.8)
        svc = LearnerModelService(config=cfg)
        learner = _learner(("calc", "some misconception"))
        result = svc.update_after_evaluation(
            learner=learner,
            topic="calc",
            correctness=0.7,
            confidence=0.8,
            misconception_description=None,
        )
        assert len([m for m in result.misconceptions if m.topic == "calc"]) == 1

    def test_resolution_does_not_fire_below_confidence_threshold(self) -> None:
        cfg = _cfg(
            misconception_resolution_correctness=0.8,
            misconception_resolution_confidence=0.6,
        )
        svc = LearnerModelService(config=cfg)
        learner = _learner(("calc", "some misconception"))
        result = svc.update_after_evaluation(
            learner=learner,
            topic="calc",
            correctness=0.9,
            confidence=0.4,  # below threshold
            misconception_description=None,
        )
        assert len([m for m in result.misconceptions if m.topic == "calc"]) == 1

    def test_resolution_does_not_fire_when_new_misconception_detected(self) -> None:
        cfg = _cfg(
            misconception_resolution_correctness=0.8,
            misconception_resolution_confidence=0.5,
        )
        svc = LearnerModelService(config=cfg)
        learner = _learner(("calc", "existing misconception"))
        result = svc.update_after_evaluation(
            learner=learner,
            topic="calc",
            correctness=0.85,
            confidence=0.7,
            misconception_description="new misconception detected",
        )
        topic_miscs = [m for m in result.misconceptions if m.topic == "calc"]
        # existing preserved + new one added = 2
        assert len(topic_miscs) == 2

    def test_resolution_only_removes_from_matching_topic(self) -> None:
        cfg = _cfg(
            misconception_resolution_correctness=0.8,
            misconception_resolution_confidence=0.5,
        )
        svc = LearnerModelService(config=cfg)
        learner = _learner(
            ("algebra", "algebra misconception"),
            ("calc", "calc misconception"),
        )
        result = svc.update_after_evaluation(
            learner=learner,
            topic="calc",
            correctness=0.9,
            confidence=0.8,
            misconception_description=None,
        )
        assert len([m for m in result.misconceptions if m.topic == "algebra"]) == 1
        assert len([m for m in result.misconceptions if m.topic == "calc"]) == 0

    def test_no_misconceptions_to_resolve_is_safe(self) -> None:
        svc = LearnerModelService()
        learner = _learner()
        result = svc.update_after_evaluation(
            learner=learner,
            topic="calc",
            correctness=0.95,
            confidence=0.9,
            misconception_description=None,
        )
        assert result.misconceptions == []
