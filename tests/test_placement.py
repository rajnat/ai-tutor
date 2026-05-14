"""Tests for prerequisite placement quiz logic."""
from unittest.mock import MagicMock

from app.models.domain import (
    Concept,
    EvaluationResult,
    GenerationTrace,
    Learner,
    LearningPreferences,
    Session,
    SessionMode,
    TeachingResponse,
    TopicState,
    TutorAction,
    TutorTurn,
)
from app.services.curriculum import CurriculumPlanner
from app.services.orchestrator import SessionOrchestrator
from app.services.tutor_config import DEFAULT_CONFIG, TutorConfig


def _learner(**skills: float) -> Learner:
    return Learner(
        name="Test",
        goal="Learn",
        learning_style=LearningPreferences(),
        skills={slug: TopicState(mastery=mastery) for slug, mastery in skills.items()},
    )


def _concept(slug: str, prerequisites: list[str] | None = None) -> Concept:
    return Concept(
        slug=slug,
        title=slug.replace("-", " ").title(),
        description="desc",
        subject="math",
        prerequisites=prerequisites or [],
    )


def _evaluation(correctness: float) -> EvaluationResult:
    return EvaluationResult(
        correctness=correctness,
        confidence=0.8,
        reasoning="test",
        trace=GenerationTrace(
            provider="fake",
            model="fake",
            prompt_version="v1",
            prompt_inputs={},
        ),
    )


def _teaching_response(text: str = "Tutor reply.") -> TeachingResponse:
    return TeachingResponse(
        text=text,
        trace=GenerationTrace(
            provider="fake",
            model="fake",
            prompt_version="v1",
            prompt_inputs={},
        ),
    )


class TestFindBlockingPrerequisite:
    def test_no_prerequisites_returns_none(self) -> None:
        planner = CurriculumPlanner()
        concept = _concept("calculus")
        learner = _learner()
        assert planner.find_blocking_prerequisite(learner, concept, [concept]) is None

    def test_met_prerequisites_returns_none(self) -> None:
        planner = CurriculumPlanner()
        prereq = _concept("algebra")
        concept = _concept("calculus", prerequisites=["algebra"])
        learner = _learner(algebra=DEFAULT_CONFIG.prerequisite_mastery_threshold)
        assert planner.find_blocking_prerequisite(learner, concept, [prereq, concept]) is None

    def test_unmet_prerequisite_returns_blocking_concept(self) -> None:
        planner = CurriculumPlanner()
        prereq = _concept("algebra")
        concept = _concept("calculus", prerequisites=["algebra"])
        learner = _learner(algebra=0.0)
        blocking = planner.find_blocking_prerequisite(learner, concept, [prereq, concept])
        assert blocking is not None
        assert blocking.slug == "algebra"

    def test_learner_with_no_skill_entry_is_treated_as_zero_mastery(self) -> None:
        planner = CurriculumPlanner()
        prereq = _concept("algebra")
        concept = _concept("calculus", prerequisites=["algebra"])
        learner = _learner()  # no algebra skill recorded
        blocking = planner.find_blocking_prerequisite(learner, concept, [prereq, concept])
        assert blocking is not None
        assert blocking.slug == "algebra"

    def test_first_unmet_prereq_blocks_even_if_later_ones_met(self) -> None:
        planner = CurriculumPlanner()
        prereq1 = _concept("algebra")
        prereq2 = _concept("trigonometry")
        concept = _concept("calculus", prerequisites=["algebra", "trigonometry"])
        learner = _learner(
            algebra=0.0,
            trigonometry=DEFAULT_CONFIG.prerequisite_mastery_threshold,
        )
        blocking = planner.find_blocking_prerequisite(learner, concept, [prereq1, prereq2, concept])
        assert blocking is not None
        assert blocking.slug == "algebra"

    def test_prerequisite_slug_not_in_concept_list_returns_none(self) -> None:
        """Gracefully handles a prereq slug that isn't in the provided concept list."""
        planner = CurriculumPlanner()
        concept = _concept("calculus", prerequisites=["algebra"])
        learner = _learner()
        # algebra concept not in all_concepts — returns None safely
        result = planner.find_blocking_prerequisite(learner, concept, [concept])
        assert result is None


def _make_orchestrator(*, config: TutorConfig = DEFAULT_CONFIG) -> SessionOrchestrator:
    teacher = MagicMock()
    teacher.respond.return_value = _teaching_response()

    learner_repo = MagicMock()
    session_repo = MagicMock()
    review_repo = MagicMock()
    review_repo.get_by_topic.return_value = None
    curriculum_repo = MagicMock()
    lesson_plan_repo = MagicMock()

    evaluator = MagicMock()
    learner_model = MagicMock()
    curriculum = CurriculumPlanner(config=config)
    review_scheduler = MagicMock()
    objective_generator = MagicMock()
    memory_service = MagicMock()
    content_library = MagicMock()
    lesson_planner = MagicMock()
    lesson_planner.get_or_create_plan.return_value = None

    orch = SessionOrchestrator(
        learner_repository=learner_repo,
        session_repository=session_repo,
        review_repository=review_repo,
        curriculum_repository=curriculum_repo,
        lesson_plan_repository=lesson_plan_repo,
        memory_service=memory_service,
        content_library=content_library,
        lesson_planner=lesson_planner,
        learner_model=learner_model,
        evaluator=evaluator,
        curriculum=curriculum,
        review_scheduler=review_scheduler,
        objective_generator=objective_generator,
        teacher=teacher,
        config=config,
    )
    return orch


class TestFinishPlacementTurn:
    def _setup(
        self,
        *,
        prereq_mastery: float = 0.0,
        turns_completed: int = 0,
        config: TutorConfig = DEFAULT_CONFIG,
    ) -> tuple[SessionOrchestrator, Learner, Session, Concept]:
        orch = _make_orchestrator(config=config)

        learner = _learner(algebra=prereq_mastery)
        # Attach mocks that save/return the input unchanged
        orch.learner_repository.save.side_effect = lambda x: x
        orch.session_repository.save.side_effect = lambda x: x

        session = Session(
            learner_id=learner.id,
            topic="algebra",
            mode=SessionMode.PLACEMENT,
            placement_topic="calculus",
        )
        for _ in range(turns_completed):
            session.turns.append(
                TutorTurn(
                    learner_message="answer",
                    tutor_action=TutorAction.ASK_DIAGNOSTIC,
                    tutor_response="Question.",
                    evaluation=_evaluation(0.3),
                )
            )

        concept = _concept("algebra")
        orch.curriculum_repository.get_by_slug.return_value = concept

        updated_learner = learner.model_copy(deep=True)
        updated_learner.skills["algebra"] = TopicState(mastery=prereq_mastery)

        return orch, learner, session, concept

    def test_placement_passes_when_mastery_meets_threshold(self) -> None:
        orch, learner, session, concept = self._setup(
            prereq_mastery=DEFAULT_CONFIG.prerequisite_mastery_threshold
        )
        updated_learner = learner.model_copy(deep=True)
        updated_learner.skills["algebra"] = TopicState(
            mastery=DEFAULT_CONFIG.prerequisite_mastery_threshold
        )

        response = orch._finish_placement_turn(
            session_id="s1",
            session=session,
            learner_message="My answer.",
            updated_learner=updated_learner,
            current_concept=concept,
            evaluation=_evaluation(0.9),
        )

        assert response.placement_passed is True
        assert session.mode == SessionMode.LEARN
        assert session.topic == "calculus"
        assert session.placement_topic is None

    def test_placement_fails_when_max_turns_reached_without_mastery(self) -> None:
        orch, learner, session, concept = self._setup(
            prereq_mastery=0.0,
            turns_completed=DEFAULT_CONFIG.placement_max_turns - 1,
        )
        updated_learner = learner.model_copy(deep=True)
        updated_learner.skills["algebra"] = TopicState(mastery=0.0)

        response = orch._finish_placement_turn(
            session_id="s1",
            session=session,
            learner_message="My answer.",
            updated_learner=updated_learner,
            current_concept=concept,
            evaluation=_evaluation(0.1),
        )

        assert response.placement_passed is False
        assert session.mode == SessionMode.LEARN
        assert session.topic == "algebra"
        assert session.placement_topic is None

    def test_placement_not_resolved_within_max_turns(self) -> None:
        """With turns remaining and mastery unmet, placement stays unresolved."""
        orch, learner, session, concept = self._setup(
            prereq_mastery=0.0,
            turns_completed=0,
        )
        updated_learner = learner.model_copy(deep=True)
        updated_learner.skills["algebra"] = TopicState(mastery=0.0)

        response = orch._finish_placement_turn(
            session_id="s1",
            session=session,
            learner_message="My answer.",
            updated_learner=updated_learner,
            current_concept=concept,
            evaluation=_evaluation(0.1),
        )

        assert response.placement_passed is None
        assert session.mode == SessionMode.PLACEMENT

    def test_placement_pass_redirects_to_original_topic(self) -> None:
        orch, learner, session, concept = self._setup(
            prereq_mastery=DEFAULT_CONFIG.prerequisite_mastery_threshold
        )
        session.placement_topic = "real-analysis"  # deeper target
        updated_learner = learner.model_copy(deep=True)
        updated_learner.skills["algebra"] = TopicState(
            mastery=DEFAULT_CONFIG.prerequisite_mastery_threshold
        )

        orch._finish_placement_turn(
            session_id="s1",
            session=session,
            learner_message="My answer.",
            updated_learner=updated_learner,
            current_concept=concept,
            evaluation=_evaluation(0.95),
        )

        assert session.topic == "real-analysis"

    def test_placement_fail_stays_on_prereq_topic(self) -> None:
        orch, learner, session, concept = self._setup(
            prereq_mastery=0.0,
            turns_completed=DEFAULT_CONFIG.placement_max_turns - 1,
        )
        updated_learner = learner.model_copy(deep=True)
        updated_learner.skills["algebra"] = TopicState(mastery=0.0)

        orch._finish_placement_turn(
            session_id="s1",
            session=session,
            learner_message="My answer.",
            updated_learner=updated_learner,
            current_concept=concept,
            evaluation=_evaluation(0.1),
        )

        assert session.topic == "algebra"
