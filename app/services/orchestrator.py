from app.models.api import LearnerResponse, SessionResponse, SubmitTurnResponse
from app.models.domain import (
    Concept,
    ConceptObjective,
    EvaluationResult,
    GenerationTrace,
    Learner,
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
    ) -> None:
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

    def _build_fallback_step(
        self,
        *,
        topic: str,
        action: TutorAction,
        focus_objective: ConceptObjective | None,
    ) -> LessonPlanStep:
        step_title = focus_objective.title if focus_objective is not None else f"Build understanding in {topic}"
        instruction = (
            f"Focus on {focus_objective.title.lower()} in {topic}."
            if focus_objective is not None
            else f"Keep building understanding in {topic} through the current exchange."
        )
        rationale = (
            "This step keeps the lesson grounded in the learner's current need until a fuller plan is available."
        )
        step_type_map = {
            TutorAction.EXPLAIN: "explain",
            TutorAction.ASK_DIAGNOSTIC: "diagnostic",
            TutorAction.ASK_PRACTICE: "practice",
            TutorAction.REINFORCE: "review",
            TutorAction.ADVANCE: "advance",
        }
        return LessonPlanStep(
            title=step_title,
            objective_id=focus_objective.id if focus_objective is not None else None,
            objective_slug=focus_objective.slug if focus_objective is not None else None,
            instruction=instruction,
            rationale=rationale,
            step_type=step_type_map[action],
        )

    def handle_turn(
        self,
        session_id: str,
        learner: Learner,
        session: Session,
        learner_message: str,
        requested_mode: SessionMode | None,
    ) -> SubmitTurnResponse:
        if requested_mode is not None:
            session.mode = requested_mode

        current_topic = session.topic
        current_concept = self.curriculum_repository.get_by_slug(current_topic)
        topic_state = self.learner_model.ensure_topic(learner, current_topic)
        evaluation_available = True
        try:
            evaluation = self.evaluator.evaluate(
                learner_message=learner_message,
                topic=current_topic,
                objectives=current_concept.objectives if current_concept is not None else None,
            )
        except LlmError as error:
            evaluation_available = False
            evaluation = EvaluationResult(
                correctness=0.5,
                confidence=0.2,
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
                if spillover_objectives and evaluation.correctness >= 0.6:
                    updated_learner.objective_states = self.objective_generator.update_objective_states(
                        updated_learner.objective_states,
                        spillover_objectives,
                        correctness=evaluation.correctness,
                        confidence=evaluation.confidence,
                        scale=0.8 if evaluation.correctness >= 0.7 else 0.35,
                    )
            else:
                updated_learner.objective_states = self.objective_generator.update_objective_states(
                    updated_learner.objective_states,
                    objective_ids,
                    correctness=evaluation.correctness,
                    confidence=evaluation.confidence,
                )

        action = self.curriculum.choose_action(
            topic=current_topic,
            mastery=topic_state.mastery,
            mode=session.mode,
            misconception_detected=evaluation.misconception_detected,
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
            try:
                lesson_plan = self.lesson_planner.get_or_create_plan(
                    learner=updated_learner,
                    concept=current_concept,
                    content_snippets=content_snippets,
                )
            except LlmError:
                lesson_plan = self.lesson_plan_repository.get_active(updated_learner.id, current_topic)
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

        if lesson_plan is not None and evaluation_available:
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
        else:
            active_lesson_step = self._build_fallback_step(
                topic=current_topic,
                action=action,
                focus_objective=focus_objective,
            )

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
