from app.models.api import LearnerResponse, SessionResponse, SubmitTurnResponse
from app.models.domain import (
    Concept,
    ConceptObjective,
    EvaluationResult,
    GenerationTrace,
    Learner,
    LearningPace,
    LessonPlan,
    LessonPlanStep,
    Session,
    SessionMode,
    TeachingResponse,
    TutorAction,
    TutorTurn,
)
from app.services.curriculum import CurriculumPlanner
from app.services.evaluation import Evaluator
from app.services.learner_model import LearnerModelService
from app.services.lesson_planner import LessonPlannerService
from app.services.llm import LlmError
from app.services.memory import LearningMemoryService
from app.services.objectives import ObjectiveGenerator
from app.services.repositories import (
    CurriculumRepository,
    LessonPlanRepository,
    LearnerRepository,
    ReviewRepository,
    SessionRepository,
)
from app.services.review import ReviewScheduler
from app.services.teaching import Teacher
from app.services.content_library import ContentLibraryService
from app.services.tutor_config import DEFAULT_CONFIG, TutorConfig


class SessionOrchestrator:
    def __init__(
        self,
        learner_repository: LearnerRepository,
        session_repository: SessionRepository,
        review_repository: ReviewRepository,
        curriculum_repository: CurriculumRepository,
        lesson_plan_repository: LessonPlanRepository,
        memory_service: LearningMemoryService,
        content_library: ContentLibraryService,
        lesson_planner: LessonPlannerService,
        learner_model: LearnerModelService,
        evaluator: Evaluator,
        curriculum: CurriculumPlanner,
        review_scheduler: ReviewScheduler,
        objective_generator: ObjectiveGenerator,
        teacher: Teacher,
        config: TutorConfig = DEFAULT_CONFIG,
    ) -> None:
        self.config = config
        self.learner_repository = learner_repository
        self.session_repository = session_repository
        self.review_repository = review_repository
        self.curriculum_repository = curriculum_repository
        self.lesson_plan_repository = lesson_plan_repository
        self.memory_service = memory_service
        self.content_library = content_library
        self.lesson_planner = lesson_planner
        self.learner_model = learner_model
        self.evaluator = evaluator
        self.curriculum = curriculum
        self.review_scheduler = review_scheduler
        self.objective_generator = objective_generator
        self.teacher = teacher

    def handle_turn(
        self,
        session_id: str,
        learner: Learner,
        session: Session,
        learner_message: str,
        requested_mode: SessionMode | None,
    ) -> SubmitTurnResponse:
        # Never allow an explicit mode change to override an in-progress placement quiz.
        if requested_mode is not None and session.mode != SessionMode.PLACEMENT:
            session.mode = requested_mode

        current_topic = session.topic
        current_concept = self.curriculum_repository.get_by_slug(current_topic)
        topic_state = self.learner_model.ensure_topic(learner, current_topic)
        last_tutor_message = session.turns[-1].tutor_response if session.turns else None
        evaluation_available = True
        try:
            evaluation = self.evaluator.evaluate(
                learner_message=learner_message,
                topic=current_topic,
                objectives=current_concept.objectives if current_concept is not None else None,
                last_tutor_message=last_tutor_message,
            )
        except LlmError as error:
            evaluation_available = False
            evaluation = EvaluationResult(
                correctness=0.5,
                confidence=self.config.degraded_evaluation_confidence,
                reasoning="Evaluation unavailable because the language model could not be reached.",
                trace=GenerationTrace(
                    provider="system",
                    model="degraded",
                    prompt_version="evaluation_unavailable_v1",
                    prompt_inputs={"error_type": type(error).__name__},
                ),
            )
        updated_learner = (
            self.learner_model.update_after_evaluation(
                learner=learner,
                topic=current_topic,
                correctness=evaluation.correctness,
                confidence=evaluation.confidence,
                misconception_description=evaluation.misconception_description,
            )
            if evaluation_available
            else learner.model_copy(deep=True)
        )
        if current_concept is not None and evaluation_available:
            objective_ids = [objective.id for objective in current_concept.objectives]
            updated_learner.objective_states = self.objective_generator.ensure_states(
                updated_learner.objective_states,
                objective_ids,
            )
            if evaluation.objective_id is not None:
                updated_learner.objective_states = self.objective_generator.update_single_objective_state(
                    updated_learner.objective_states,
                    objective_id=evaluation.objective_id,
                    correctness=evaluation.correctness,
                    confidence=evaluation.confidence,
                )
                spillover_objectives = [
                    objective_id for objective_id in objective_ids if objective_id != evaluation.objective_id
                ]
                cfg = self.config
                if spillover_objectives and evaluation.correctness >= cfg.spillover_min_correctness:
                    updated_learner.objective_states = self.objective_generator.update_objective_states(
                        updated_learner.objective_states,
                        spillover_objectives,
                        correctness=evaluation.correctness,
                        confidence=evaluation.confidence,
                        scale=cfg.spillover_scale_high if evaluation.correctness >= cfg.spillover_high_boundary else cfg.spillover_scale_low,
                    )
            else:
                updated_learner.objective_states = self.objective_generator.update_objective_states(
                    updated_learner.objective_states,
                    objective_ids,
                    correctness=evaluation.correctness,
                    confidence=evaluation.confidence,
                )

        if session.mode == SessionMode.PLACEMENT:
            return self._finish_placement_turn(
                session_id=session_id,
                session=session,
                learner_message=learner_message,
                updated_learner=updated_learner,
                current_concept=current_concept,
                evaluation=evaluation,
            )

        topic_misconceptions = [m for m in updated_learner.misconceptions if m.topic == current_topic]
        recent_misconception_count = len(topic_misconceptions[-self.config.difficulty_misconception_window :])
        learning_pace = self.curriculum.assess_learning_pace(
            recent_turns=session.turns,
            mastery=topic_state.mastery,
        )
        action = self.curriculum.choose_action(
            topic=current_topic,
            mastery=topic_state.mastery,
            mode=session.mode,
            misconception_detected=evaluation.misconception_detected,
            confidence=topic_state.confidence,
            recent_misconception_count=recent_misconception_count,
            learning_pace=learning_pace,
        )
        if action == TutorAction.ADVANCE and not self.curriculum.concept_ready_to_advance(
            updated_learner, current_concept
        ):
            action = TutorAction.ASK_DIAGNOSTIC

        focus_objective: ConceptObjective | None = self.curriculum.weakest_objective(
            updated_learner, current_concept
        )
        memory_context = self.memory_service.build_context(
            learner=updated_learner,
            topic=current_topic,
            focus_objective=focus_objective,
            current_session=session,
        )
        content_snippets = []
        lesson_plan: LessonPlan | None = None
        if current_concept is not None:
            lesson_plan = self.lesson_planner.get_or_create_plan(
                learner=updated_learner,
                concept=current_concept,
                content_snippets=content_snippets,
            )
        next_concept: Concept | None = None
        if action == TutorAction.ADVANCE:
            concepts = self.curriculum_repository.list_concepts()
            next_concept = self.curriculum.choose_next_concept(
                current_topic=current_topic,
                learner=updated_learner,
                concepts=concepts,
            )
            if next_concept is not None:
                session.topic = next_concept.slug

        if lesson_plan is not None:
            lesson_plan = self.lesson_planner.advance_progress(
                lesson_plan,
                action=action.value,
                correctness=evaluation.correctness,
                focus_objective_id=focus_objective.id if focus_objective is not None else None,
                topic_ready_to_advance=self.curriculum.concept_ready_to_advance(updated_learner, current_concept),
            )
        active_lesson_step = None
        if lesson_plan is not None and lesson_plan.steps:
            active_index = min(max(lesson_plan.current_step_index, 0), len(lesson_plan.steps) - 1)
            active_lesson_step = lesson_plan.steps[active_index]

        try:
            teaching_response = self.teacher.respond(
                learner=updated_learner,
                topic=current_topic,
                action=action,
                learner_message=learner_message,
                mode=session.mode,
                current_concept=current_concept,
                next_concept=next_concept,
                focus_objective=focus_objective,
                recent_turns=session.turns,
                memory_context=memory_context,
                content_snippets=content_snippets,
                lesson_plan=lesson_plan,
                active_lesson_step=active_lesson_step,
                learning_pace=learning_pace,
            )
        except LlmError as error:
            teaching_response = TeachingResponse(
                text=(
                    f"I hit a temporary issue while preparing the next step in {current_topic}. "
                    "Please try once more, or tell me the part that still feels most confusing and I’ll continue from there."
                ),
                trace=GenerationTrace(
                    provider="system",
                    model="degraded",
                    prompt_version="teaching_unavailable_v1",
                    prompt_inputs={"error_type": type(error).__name__, "topic": current_topic},
                ),
            )
        tutor_response = teaching_response.text

        session.turns.append(
            TutorTurn(
                learner_message=learner_message,
                tutor_action=action,
                tutor_response=tutor_response,
                evaluation=evaluation,
                teaching_trace=teaching_response.trace,
            )
        )

        saved_learner = self.learner_repository.save(updated_learner)
        saved_session = self.session_repository.save(session)
        existing_review = self.review_repository.get_by_topic(saved_learner.id, current_topic)
        review_item = self.review_scheduler.schedule_after_turn(
            learner_id=saved_learner.id,
            topic=current_topic,
            correctness=evaluation.correctness,
            existing=existing_review,
            concept=current_concept,
            focus_objective=focus_objective,
        )
        self.review_repository.save(review_item)

        return SubmitTurnResponse(
            session_id=session_id,
            tutor_action=action,
            tutor_response=tutor_response,
            evaluation=evaluation,
            active_lesson_step=active_lesson_step,
            updated_learner=LearnerResponse.model_validate(saved_learner),
            updated_session=SessionResponse.model_validate(saved_session),
        )

    def _finish_placement_turn(
        self,
        session_id: str,
        session: Session,
        learner_message: str,
        updated_learner: Learner,
        current_concept: Concept | None,
        evaluation: EvaluationResult,
    ) -> SubmitTurnResponse:
        prereq_topic = session.topic
        updated_prereq_state = updated_learner.skills.get(prereq_topic)
        prereq_mastery = updated_prereq_state.mastery if updated_prereq_state is not None else 0.0
        prereq_cleared = prereq_mastery >= self.config.prerequisite_mastery_threshold

        # session.turns does not yet include the current turn, so len() is turns completed so far.
        hit_max = len(session.turns) >= self.config.placement_max_turns - 1

        placement_resolved = prereq_cleared or hit_max
        placement_passed: bool | None = None
        action = TutorAction.ASK_DIAGNOSTIC

        if placement_resolved:
            placement_passed = prereq_cleared
            original_topic = session.placement_topic or prereq_topic
            if prereq_cleared:
                # Learner demonstrated prerequisite knowledge — move to the requested topic.
                session.topic = original_topic
            # If not cleared, stay on the prereq topic and switch to LEARN so the tutor
            # teaches it rather than continuing to assess.
            session.mode = SessionMode.LEARN
            session.placement_topic = None
            action = TutorAction.EXPLAIN

        focus_objective = self.curriculum.weakest_objective(updated_learner, current_concept)
        try:
            teaching_response = self.teacher.respond(
                learner=updated_learner,
                topic=session.topic,
                action=action,
                learner_message=learner_message,
                mode=SessionMode.PLACEMENT if not placement_resolved else SessionMode.LEARN,
                current_concept=self.curriculum_repository.get_by_slug(session.topic),
                focus_objective=focus_objective,
                recent_turns=session.turns,
            )
        except LlmError as error:
            teaching_response = TeachingResponse(
                text=(
                    "I hit a temporary issue. Please try again."
                ),
                trace=GenerationTrace(
                    provider="system",
                    model="degraded",
                    prompt_version="teaching_unavailable_v1",
                    prompt_inputs={"error_type": type(error).__name__, "topic": session.topic},
                ),
            )

        session.turns.append(
            TutorTurn(
                learner_message=learner_message,
                tutor_action=action,
                tutor_response=teaching_response.text,
                evaluation=evaluation,
                teaching_trace=teaching_response.trace,
            )
        )

        saved_learner = self.learner_repository.save(updated_learner)
        saved_session = self.session_repository.save(session)

        return SubmitTurnResponse(
            session_id=session_id,
            tutor_action=action,
            tutor_response=teaching_response.text,
            evaluation=evaluation,
            active_lesson_step=None,
            updated_learner=LearnerResponse.model_validate(saved_learner),
            updated_session=SessionResponse.model_validate(saved_session),
            placement_passed=placement_passed,
        )
