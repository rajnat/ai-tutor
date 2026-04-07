from app.models.api import LearnerResponse, SessionResponse, SubmitTurnResponse
from app.models.domain import Concept, ConceptObjective, Learner, Session, SessionMode, TutorAction, TutorTurn
from app.services.curriculum import CurriculumPlanner
from app.services.evaluation import EvaluationService
from app.services.learner_model import LearnerModelService
from app.services.objectives import ObjectiveGenerator
from app.services.repositories import (
    CurriculumRepository,
    LearnerRepository,
    ReviewRepository,
    SessionRepository,
)
from app.services.review import ReviewScheduler
from app.services.teaching import TeachingService


class SessionOrchestrator:
    def __init__(
        self,
        learner_repository: LearnerRepository,
        session_repository: SessionRepository,
        review_repository: ReviewRepository,
        curriculum_repository: CurriculumRepository,
        learner_model: LearnerModelService,
        evaluator: EvaluationService,
        curriculum: CurriculumPlanner,
        review_scheduler: ReviewScheduler,
        objective_generator: ObjectiveGenerator,
        teacher: TeachingService,
    ) -> None:
        self.learner_repository = learner_repository
        self.session_repository = session_repository
        self.review_repository = review_repository
        self.curriculum_repository = curriculum_repository
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
        if requested_mode is not None:
            session.mode = requested_mode

        current_topic = session.topic
        current_concept = self.curriculum_repository.get_by_slug(current_topic)
        topic_state = self.learner_model.ensure_topic(learner, current_topic)
        evaluation = self.evaluator.evaluate(
            learner_message=learner_message,
            topic=current_topic,
            objectives=current_concept.objectives if current_concept is not None else None,
        )
        updated_learner = self.learner_model.update_after_evaluation(
            learner=learner,
            topic=current_topic,
            correctness=evaluation.correctness,
            confidence=evaluation.confidence,
            misconception_description=evaluation.misconception_description,
        )
        if current_concept is not None:
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

        tutor_response = self.teacher.respond(
            learner=updated_learner,
            topic=current_topic,
            action=action,
            learner_message=learner_message,
            mode=session.mode,
            next_concept=next_concept,
            focus_objective=focus_objective,
        )

        session.turns.append(
            TutorTurn(
                learner_message=learner_message,
                tutor_action=action,
                tutor_response=tutor_response,
                evaluation=evaluation,
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
        )
        self.review_repository.save(review_item)

        return SubmitTurnResponse(
            session_id=session_id,
            tutor_action=action,
            tutor_response=tutor_response,
            evaluation=evaluation,
            updated_learner=LearnerResponse.model_validate(saved_learner),
            updated_session=SessionResponse.model_validate(saved_session),
        )
