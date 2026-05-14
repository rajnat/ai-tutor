from app.models.domain import (
    EvaluationResult,
    LearningPace,
    SessionMode,
    TutorAction,
    TutorTurn,
)
from app.services.curriculum import CurriculumPlanner
from app.services.tutor_config import TutorConfig


def _turn(correctness: float, misconception: bool = False) -> TutorTurn:
    return TutorTurn(
        learner_message="answer",
        tutor_action=TutorAction.ASK_DIAGNOSTIC,
        tutor_response="response",
        evaluation=EvaluationResult(
            correctness=correctness,
            confidence=0.5,
            misconception_detected=misconception,
            reasoning="test",
        ),
    )


_cfg = TutorConfig()
_planner = CurriculumPlanner(config=_cfg)


class TestChooseAction:
    def test_baseline_novice_explains(self) -> None:
        action = _planner.choose_action(
            topic="algebra", mastery=0.1, mode=SessionMode.LEARN,
            misconception_detected=False,
        )
        assert action == TutorAction.EXPLAIN

    def test_baseline_intermediate_asks_diagnostic(self) -> None:
        action = _planner.choose_action(
            topic="algebra", mastery=0.5, mode=SessionMode.LEARN,
            misconception_detected=False,
        )
        assert action == TutorAction.ASK_DIAGNOSTIC

    def test_baseline_high_mastery_advances(self) -> None:
        action = _planner.choose_action(
            topic="algebra", mastery=0.85, mode=SessionMode.LEARN,
            misconception_detected=False, confidence=0.8,
        )
        assert action == TutorAction.ADVANCE

    def test_current_turn_misconception_forces_reinforce(self) -> None:
        action = _planner.choose_action(
            topic="algebra", mastery=0.5, mode=SessionMode.LEARN,
            misconception_detected=True,
        )
        assert action == TutorAction.REINFORCE

    def test_accumulated_misconceptions_force_reinforce(self) -> None:
        """Two misconceptions on the topic → REINFORCE even at intermediate mastery."""
        action = _planner.choose_action(
            topic="algebra", mastery=0.5, mode=SessionMode.LEARN,
            misconception_detected=False,
            recent_misconception_count=2,
        )
        assert action == TutorAction.REINFORCE

    def test_accumulated_misconceptions_override_high_mastery(self) -> None:
        """Even high mastery with accumulated misconceptions → REINFORCE."""
        action = _planner.choose_action(
            topic="algebra", mastery=0.85, mode=SessionMode.LEARN,
            misconception_detected=False,
            recent_misconception_count=3,
            confidence=0.8,
        )
        assert action == TutorAction.REINFORCE

    def test_low_confidence_blocks_advance(self) -> None:
        """Mastery high enough to ADVANCE but confidence too low → ASK_DIAGNOSTIC."""
        action = _planner.choose_action(
            topic="algebra", mastery=0.85, mode=SessionMode.LEARN,
            misconception_detected=False,
            confidence=0.2,
        )
        assert action == TutorAction.ASK_DIAGNOSTIC

    def test_sufficient_confidence_allows_advance(self) -> None:
        action = _planner.choose_action(
            topic="algebra", mastery=0.85, mode=SessionMode.LEARN,
            misconception_detected=False,
            confidence=0.6,
        )
        assert action == TutorAction.ADVANCE

    def test_struggling_demotes_advance_to_diagnostic(self) -> None:
        action = _planner.choose_action(
            topic="algebra", mastery=0.85, mode=SessionMode.LEARN,
            misconception_detected=False,
            confidence=0.8,
            learning_pace=LearningPace.STRUGGLING,
        )
        assert action == TutorAction.ASK_DIAGNOSTIC

    def test_struggling_demotes_diagnostic_to_explain(self) -> None:
        action = _planner.choose_action(
            topic="algebra", mastery=0.5, mode=SessionMode.LEARN,
            misconception_detected=False,
            learning_pace=LearningPace.STRUGGLING,
        )
        assert action == TutorAction.EXPLAIN

    def test_struggling_does_not_demote_explain_further(self) -> None:
        """EXPLAIN is the floor — STRUGGLING should not drop below it."""
        action = _planner.choose_action(
            topic="algebra", mastery=0.1, mode=SessionMode.LEARN,
            misconception_detected=False,
            learning_pace=LearningPace.STRUGGLING,
        )
        assert action == TutorAction.EXPLAIN

    def test_accelerating_promotes_explain_to_diagnostic(self) -> None:
        action = _planner.choose_action(
            topic="algebra", mastery=0.1, mode=SessionMode.LEARN,
            misconception_detected=False,
            learning_pace=LearningPace.ACCELERATING,
        )
        assert action == TutorAction.ASK_DIAGNOSTIC

    def test_accelerating_does_not_affect_diagnostic_or_advance(self) -> None:
        """ACCELERATING only promotes EXPLAIN; higher actions are unaffected."""
        diag = _planner.choose_action(
            topic="algebra", mastery=0.5, mode=SessionMode.LEARN,
            misconception_detected=False,
            learning_pace=LearningPace.ACCELERATING,
        )
        assert diag == TutorAction.ASK_DIAGNOSTIC

        adv = _planner.choose_action(
            topic="algebra", mastery=0.85, mode=SessionMode.LEARN,
            misconception_detected=False,
            confidence=0.8,
            learning_pace=LearningPace.ACCELERATING,
        )
        assert adv == TutorAction.ADVANCE

    def test_mode_test_always_practice(self) -> None:
        for pace in LearningPace:
            action = _planner.choose_action(
                topic="algebra", mastery=0.85, mode=SessionMode.TEST,
                misconception_detected=False,
                learning_pace=pace,
            )
            assert action == TutorAction.ASK_PRACTICE


class TestAssessLearningPace:
    def test_empty_turns_returns_normal(self) -> None:
        pace = _planner.assess_learning_pace(recent_turns=[], mastery=0.2)
        assert pace == LearningPace.NORMAL

    def test_low_avg_correctness_returns_struggling(self) -> None:
        turns = [_turn(0.3), _turn(0.2), _turn(0.35), _turn(0.25)]
        pace = _planner.assess_learning_pace(recent_turns=turns, mastery=0.2)
        assert pace == LearningPace.STRUGGLING

    def test_high_avg_correctness_returns_accelerating(self) -> None:
        turns = [_turn(0.8), _turn(0.9), _turn(0.85), _turn(0.92)]
        pace = _planner.assess_learning_pace(recent_turns=turns, mastery=0.5)
        assert pace == LearningPace.ACCELERATING

    def test_moderate_correctness_returns_normal(self) -> None:
        turns = [_turn(0.55), _turn(0.6), _turn(0.5), _turn(0.65)]
        pace = _planner.assess_learning_pace(recent_turns=turns, mastery=0.4)
        assert pace == LearningPace.NORMAL

    def test_stuck_at_novice_after_many_turns(self) -> None:
        """Many turns with decent correctness but mastery still novice → STRUGGLING."""
        turns = [_turn(0.5)] * _cfg.pace_struggling_turns_minimum
        pace = _planner.assess_learning_pace(
            recent_turns=turns,
            mastery=_cfg.mastery_novice_threshold - 0.01,
        )
        assert pace == LearningPace.STRUGGLING

    def test_novice_mastery_not_struggling_before_minimum_turns(self) -> None:
        """The stuck-at-novice guard must not fire before enough turns have accumulated."""
        turns = [_turn(0.5)] * (_cfg.pace_struggling_turns_minimum - 1)
        pace = _planner.assess_learning_pace(
            recent_turns=turns,
            mastery=_cfg.mastery_novice_threshold - 0.01,
        )
        # avg correctness is 0.5 which is above struggling threshold (0.4) → NORMAL
        assert pace == LearningPace.NORMAL

    def test_uses_only_recent_window(self) -> None:
        """Old poor turns should not drag the pace down if recent ones are strong."""
        old_poor = [_turn(0.1)] * 10
        recent_strong = [_turn(0.9)] * _cfg.pace_recent_turns_window
        turns = old_poor + recent_strong
        pace = _planner.assess_learning_pace(recent_turns=turns, mastery=0.5)
        assert pace == LearningPace.ACCELERATING
