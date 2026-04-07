from app.models.api import LearnerResponse, SessionResponse, SubmitTurnResponse
from app.models.domain import Learner, Session, SessionMode, TutorTurn
from app.services.curriculum import CurriculumPlanner
from app.services.evaluation import EvaluationService
from app.services.learner_model import LearnerModelService
from app.services.repositories import LearnerRepository, SessionRepository
from app.services.teaching import TeachingService


class SessionOrchestrator:
    def __init__(
        self,
        learner_repository: LearnerRepository,
        session_repository: SessionRepository,
        learner_model: LearnerModelService,
        evaluator: EvaluationService,
        curriculum: CurriculumPlanner,
        teacher: TeachingService,
    ) -> None:
        self.learner_repository = learner_repository
        self.session_repository = session_repository
        self.learner_model = learner_model
        self.evaluator = evaluator
        self.curriculum = curriculum
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

        topic_state = self.learner_model.ensure_topic(learner, session.topic)
        evaluation = self.evaluator.evaluate(learner_message=learner_message, topic=session.topic)
        updated_learner = self.learner_model.update_after_evaluation(
            learner=learner,
            topic=session.topic,
            correctness=evaluation.correctness,
            confidence=evaluation.confidence,
            misconception_description=evaluation.misconception_description,
        )

        action = self.curriculum.choose_action(
            topic=session.topic,
            mastery=topic_state.mastery,
            mode=session.mode,
            misconception_detected=evaluation.misconception_detected,
        )
        tutor_response = self.teacher.respond(
            learner=updated_learner,
            topic=session.topic,
            action=action,
            learner_message=learner_message,
            mode=session.mode,
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

        return SubmitTurnResponse(
            session_id=session_id,
            tutor_action=action,
            tutor_response=tutor_response,
            evaluation=evaluation,
            updated_learner=LearnerResponse.model_validate(saved_learner),
            updated_session=SessionResponse.model_validate(saved_session),
        )
