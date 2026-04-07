from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession, selectinload

from app.models.api import CreateLearnerRequest, CreateSessionRequest
from app.models.domain import (
    Account,
    AuthSession,
    AuthSessionStatus,
    Concept,
    ConceptObjective,
    EvaluationResult,
    GenerationTrace,
    Learner,
    LearningPreferences,
    LessonPlan,
    LessonPlanStep,
    Misconception,
    ObjectiveState,
    ReviewItem,
    ReviewStatus,
    Session,
    SessionMode,
    TutorAction,
    TopicState,
    TutorTurn,
)
from app.services.orm import (
    AccountRecord,
    AuthSessionRecord,
    ConceptObjectiveRecord,
    ConceptPrerequisiteRecord,
    ConceptRecord,
    LessonPlanRecord,
    LessonPlanStepRecord,
    LearnerMisconceptionRecord,
    LearnerObjectiveStateRecord,
    LearnerRecord,
    LearnerTopicStateRecord,
    ReviewItemRecord,
    SessionRecord,
    SessionTurnRecord,
)


class LearnerRepository(Protocol):
    def create(self, payload: CreateLearnerRequest) -> Learner: ...
    def get(self, learner_id: str) -> Learner | None: ...
    def save(self, learner: Learner) -> Learner: ...


class SessionRepository(Protocol):
    def create(self, payload: CreateSessionRequest) -> Session: ...
    def get(self, session_id: str) -> Session | None: ...
    def list_for_learner(self, learner_id: str, limit: int = 10) -> list[Session]: ...
    def save(self, session: Session) -> Session: ...


class ReviewRepository(Protocol):
    def get_due_reviews(self, learner_id: str) -> list[ReviewItem]: ...
    def get_by_topic(self, learner_id: str, topic: str) -> ReviewItem | None: ...
    def get(self, review_id: str) -> ReviewItem | None: ...
    def save(self, review_item: ReviewItem) -> ReviewItem: ...


class CurriculumRepository(Protocol):
    def create_concept(self, concept: Concept) -> Concept: ...
    def list_concepts(self, subject: str | None = None) -> list[Concept]: ...
    def get_by_slug(self, slug: str) -> Concept | None: ...


class LessonPlanRepository(Protocol):
    def get_active(self, learner_id: str, topic: str) -> LessonPlan | None: ...
    def save(self, lesson_plan: LessonPlan) -> LessonPlan: ...
    def supersede_active(self, learner_id: str, topic: str) -> None: ...


class AccountRepository(Protocol):
    def create(self, account: Account, password_hash: str) -> Account: ...
    def get_by_email(self, email: str) -> tuple[Account, str] | None: ...
    def get(self, account_id: str) -> Account | None: ...
    def create_session(self, auth_session: AuthSession, token_hash: str) -> AuthSession: ...
    def get_session(self, token_hash: str) -> AuthSession | None: ...
    def revoke_session(self, token_hash: str) -> None: ...


def _learner_from_record(record: LearnerRecord) -> Learner:
    skills = {
        state.topic: TopicState(
            mastery=state.mastery,
            confidence=state.confidence,
            last_practiced_at=state.last_practiced_at,
        )
        for state in record.topic_states
    }
    return Learner(
        id=record.id,
        name=record.name,
        goal=record.goal,
        skills=skills,
        objective_states={
            state.objective_id: ObjectiveState(
                mastery=state.mastery,
                confidence=state.confidence,
                last_practiced_at=state.last_practiced_at,
            )
            for state in record.objective_states
        },
        misconceptions=[
            Misconception(
                topic=item.topic,
                description=item.description,
                severity=item.severity,
                created_at=item.created_at,
            )
            for item in record.misconceptions
        ],
        learning_style=LearningPreferences.model_validate(record.learning_style or {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _session_from_record(record: SessionRecord) -> Session:
    return Session(
        id=record.id,
        learner_id=record.learner_id,
        topic=record.topic,
        mode=SessionMode(record.mode),
        turns=[
            TutorTurn(
                id=turn.id,
                learner_message=turn.learner_message,
                tutor_action=TutorAction(turn.tutor_action),
                tutor_response=turn.tutor_response,
                evaluation=EvaluationResult(
                    correctness=turn.correctness,
                    confidence=turn.confidence,
                    objective_id=turn.objective_id,
                    misconception_detected=turn.misconception_detected,
                    misconception_description=turn.misconception_description,
                    reasoning=turn.reasoning,
                    trace=GenerationTrace.model_validate(turn.evaluation_trace)
                    if turn.evaluation_trace
                    else None,
                ),
                teaching_trace=GenerationTrace.model_validate(turn.teaching_trace)
                if turn.teaching_trace
                else None,
                created_at=turn.created_at,
            )
            for turn in record.turns
        ],
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _review_from_record(record: ReviewItemRecord) -> ReviewItem:
    return ReviewItem(
        id=record.id,
        learner_id=record.learner_id,
        topic=record.topic,
        due_at=record.due_at,
        status=ReviewStatus(record.status),
        interval_days=record.interval_days,
        review_count=record.review_count,
        last_reviewed_at=record.last_reviewed_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _concept_from_record(record: ConceptRecord) -> Concept:
    return Concept(
        id=record.id,
        slug=record.slug,
        title=record.title,
        description=record.description,
        subject=record.subject,
        prerequisites=[link.prerequisite_id for link in record.prerequisite_links],
        objectives=[
            ConceptObjective(
                id=objective.id,
                concept_id=objective.concept_id,
                slug=objective.slug,
                title=objective.title,
                description=objective.description,
                mastery_threshold=objective.mastery_threshold,
            )
            for objective in record.objectives
        ],
        created_at=record.created_at,
    )


def _account_from_record(record: AccountRecord) -> Account:
    return Account(
        id=record.id,
        email=record.email,
        learner_id=record.learner_id,
        created_at=record.created_at,
    )


def _auth_session_from_record(record: AuthSessionRecord) -> AuthSession:
    return AuthSession(
        id=record.id,
        account_id=record.account_id,
        token="",
        expires_at=record.expires_at,
        status=AuthSessionStatus(record.status),
        created_at=record.created_at,
    )


def _lesson_plan_from_record(record: LessonPlanRecord) -> LessonPlan:
    return LessonPlan(
        id=record.id,
        learner_id=record.learner_id,
        topic=record.topic,
        status=record.status,
        summary=record.summary,
        steps=[
            LessonPlanStep(
                id=step.id,
                title=step.title,
                objective_id=step.objective_id,
                objective_slug=step.objective_slug,
                instruction=step.instruction,
                rationale=step.rationale,
                step_type=step.step_type,
            )
            for step in record.steps
        ],
        current_step_index=record.current_step_index,
        completed_step_ids=list(record.completed_step_ids or []),
        trace=GenerationTrace.model_validate(record.trace) if record.trace else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )

def _learner_query():
    return select(LearnerRecord).options(
        selectinload(LearnerRecord.topic_states),
        selectinload(LearnerRecord.objective_states),
        selectinload(LearnerRecord.misconceptions),
    )


def _session_query():
    return select(SessionRecord).options(selectinload(SessionRecord.turns))


def _concept_query():
    return select(ConceptRecord).options(
        selectinload(ConceptRecord.prerequisite_links),
        selectinload(ConceptRecord.objectives),
    )


def _lesson_plan_query():
    return select(LessonPlanRecord).options(selectinload(LessonPlanRecord.steps))


class SqlLearnerRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def create(self, payload: CreateLearnerRequest) -> Learner:
        learner = Learner(
            name=payload.name,
            goal=payload.goal,
            learning_style=payload.preferences,
        )
        if payload.initial_topic:
            learner.skills[payload.initial_topic] = TopicState(mastery=0.2, confidence=0.2)

        record = LearnerRecord(
            id=learner.id,
            name=learner.name,
            goal=learner.goal,
            learning_style=learner.learning_style.model_dump(mode="json"),
            created_at=learner.created_at,
            updated_at=learner.updated_at,
        )
        record.topic_states = [
            LearnerTopicStateRecord(
                topic=topic,
                mastery=state.mastery,
                confidence=state.confidence,
                last_practiced_at=state.last_practiced_at,
            )
            for topic, state in learner.skills.items()
        ]
        self.db.add(record)
        self.db.commit()
        return self.get(learner.id) or learner

    def get(self, learner_id: str) -> Learner | None:
        record = self.db.execute(_learner_query().where(LearnerRecord.id == learner_id)).scalar_one_or_none()
        if record is None:
            return None
        return _learner_from_record(record)

    def save(self, learner: Learner) -> Learner:
        record = self.db.get(LearnerRecord, learner.id)
        if record is None:
            raise ValueError(f"Learner {learner.id} not found")

        record.name = learner.name
        record.goal = learner.goal
        record.learning_style = learner.learning_style.model_dump(mode="json")
        record.created_at = learner.created_at
        record.updated_at = learner.updated_at
        record.topic_states.clear()
        self.db.flush()
        record.topic_states.extend(
            [
                LearnerTopicStateRecord(
                    topic=topic,
                    mastery=state.mastery,
                    confidence=state.confidence,
                    last_practiced_at=state.last_practiced_at,
                )
                for topic, state in learner.skills.items()
            ]
        )
        record.objective_states.clear()
        self.db.flush()
        record.objective_states.extend(
            [
                LearnerObjectiveStateRecord(
                    objective_id=objective_id,
                    mastery=state.mastery,
                    confidence=state.confidence,
                    last_practiced_at=state.last_practiced_at,
                )
                for objective_id, state in learner.objective_states.items()
            ]
        )
        record.misconceptions.clear()
        self.db.flush()
        record.misconceptions.extend(
            [
                LearnerMisconceptionRecord(
                    topic=item.topic,
                    description=item.description,
                    severity=item.severity,
                    created_at=item.created_at,
                )
                for item in learner.misconceptions
            ]
        )

        self.db.add(record)
        self.db.commit()
        return self.get(learner.id) or learner


class SqlSessionRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def create(self, payload: CreateSessionRequest) -> Session:
        session = Session(
            learner_id=payload.learner_id,
            topic=payload.topic,
            mode=payload.mode,
        )

        record = SessionRecord(
            id=session.id,
            learner_id=session.learner_id,
            topic=session.topic,
            mode=session.mode.value,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
        self.db.add(record)
        self.db.commit()
        return self.get(session.id) or session

    def get(self, session_id: str) -> Session | None:
        record = self.db.execute(_session_query().where(SessionRecord.id == session_id)).scalar_one_or_none()
        if record is None:
            return None
        return _session_from_record(record)

    def list_for_learner(self, learner_id: str, limit: int = 10) -> list[Session]:
        records = self.db.execute(
            _session_query()
            .where(SessionRecord.learner_id == learner_id)
            .order_by(SessionRecord.updated_at.desc())
            .limit(limit)
        ).scalars().all()
        return [_session_from_record(record) for record in records]

    def save(self, session: Session) -> Session:
        record = self.db.get(SessionRecord, session.id)
        if record is None:
            raise ValueError(f"Session {session.id} not found")

        record.topic = session.topic
        record.mode = session.mode.value
        record.created_at = session.created_at
        record.updated_at = session.updated_at
        record.turns.clear()
        self.db.flush()
        record.turns.extend(
            [
                SessionTurnRecord(
                    id=turn.id,
                    learner_message=turn.learner_message,
                    tutor_action=turn.tutor_action.value,
                    tutor_response=turn.tutor_response,
                    correctness=turn.evaluation.correctness,
                    confidence=turn.evaluation.confidence,
                    objective_id=turn.evaluation.objective_id,
                    misconception_detected=turn.evaluation.misconception_detected,
                    misconception_description=turn.evaluation.misconception_description,
                    reasoning=turn.evaluation.reasoning,
                    evaluation_trace=turn.evaluation.trace.model_dump(mode="json")
                    if turn.evaluation.trace
                    else None,
                    teaching_trace=turn.teaching_trace.model_dump(mode="json")
                    if turn.teaching_trace
                    else None,
                    created_at=turn.created_at,
                )
                for turn in session.turns
            ]
        )

        self.db.add(record)
        self.db.commit()
        return self.get(session.id) or session


class SqlReviewRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def get_due_reviews(self, learner_id: str) -> list[ReviewItem]:
        records = self.db.execute(
            select(ReviewItemRecord)
            .where(ReviewItemRecord.learner_id == learner_id, ReviewItemRecord.status == ReviewStatus.DUE.value)
            .order_by(ReviewItemRecord.due_at.asc())
        ).scalars()
        return [_review_from_record(record) for record in records]

    def get_by_topic(self, learner_id: str, topic: str) -> ReviewItem | None:
        record = self.db.execute(
            select(ReviewItemRecord).where(
                ReviewItemRecord.learner_id == learner_id,
                ReviewItemRecord.topic == topic,
            )
        ).scalar_one_or_none()
        return _review_from_record(record) if record is not None else None

    def get(self, review_id: str) -> ReviewItem | None:
        record = self.db.get(ReviewItemRecord, review_id)
        return _review_from_record(record) if record is not None else None

    def save(self, review_item: ReviewItem) -> ReviewItem:
        record = self.db.get(ReviewItemRecord, review_item.id)
        if record is None:
            record = ReviewItemRecord(
                id=review_item.id,
                learner_id=review_item.learner_id,
                topic=review_item.topic,
                due_at=review_item.due_at,
                status=review_item.status.value,
                interval_days=review_item.interval_days,
                review_count=review_item.review_count,
                last_reviewed_at=review_item.last_reviewed_at,
                created_at=review_item.created_at,
                updated_at=review_item.updated_at,
            )
        else:
            record.topic = review_item.topic
            record.due_at = review_item.due_at
            record.status = review_item.status.value
            record.interval_days = review_item.interval_days
            record.review_count = review_item.review_count
            record.last_reviewed_at = review_item.last_reviewed_at
            record.updated_at = review_item.updated_at

        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return _review_from_record(record)


class SqlCurriculumRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def create_concept(self, concept: Concept) -> Concept:
        prerequisite_records = []
        if concept.prerequisites:
            prerequisite_records = self.db.execute(
                select(ConceptRecord).where(ConceptRecord.slug.in_(concept.prerequisites))
            ).scalars().all()

        record = ConceptRecord(
            id=concept.id,
            slug=concept.slug,
            title=concept.title,
            description=concept.description,
            subject=concept.subject,
            created_at=concept.created_at,
        )
        record.prerequisite_links = [
            ConceptPrerequisiteRecord(prerequisite_id=prereq.id) for prereq in prerequisite_records
        ]
        record.objectives = [
            ConceptObjectiveRecord(
                id=objective.id,
                slug=objective.slug,
                title=objective.title,
                description=objective.description,
                mastery_threshold=objective.mastery_threshold,
            )
            for objective in concept.objectives
        ]
        self.db.add(record)
        self.db.commit()
        return self.list_concepts(subject=concept.subject, slugs=[concept.slug])[0]

    def get_by_slug(self, slug: str) -> Concept | None:
        concepts = self.list_concepts(slugs=[slug])
        return concepts[0] if concepts else None

    def list_concepts(
        self,
        subject: str | None = None,
        slugs: list[str] | None = None,
    ) -> list[Concept]:
        query = _concept_query()
        if subject is not None:
            query = query.where(ConceptRecord.subject == subject)
        if slugs is not None:
            query = query.where(ConceptRecord.slug.in_(slugs))

        records = self.db.execute(query.order_by(ConceptRecord.slug.asc())).scalars().all()
        prerequisite_ids = {
            link.prerequisite_id
            for record in records
            for link in record.prerequisite_links
        }
        prerequisite_slug_map: dict[str, str] = {}
        if prerequisite_ids:
            prerequisite_records = self.db.execute(
                select(ConceptRecord).where(ConceptRecord.id.in_(prerequisite_ids))
            ).scalars().all()
            prerequisite_slug_map = {record.id: record.slug for record in prerequisite_records}

        concepts = []
        for record in records:
            concepts.append(
                Concept(
                    id=record.id,
                    slug=record.slug,
                    title=record.title,
                    description=record.description,
                    subject=record.subject,
                    prerequisites=[
                        prerequisite_slug_map.get(link.prerequisite_id)
                        for link in record.prerequisite_links
                        if prerequisite_slug_map.get(link.prerequisite_id) is not None
                    ],
                    objectives=[
                        ConceptObjective(
                            id=objective.id,
                            concept_id=objective.concept_id,
                            slug=objective.slug,
                            title=objective.title,
                            description=objective.description,
                            mastery_threshold=objective.mastery_threshold,
                        )
                        for objective in record.objectives
                    ],
                    created_at=record.created_at,
                )
            )
        return concepts


class SqlLessonPlanRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def get_active(self, learner_id: str, topic: str) -> LessonPlan | None:
        record = self.db.execute(
            _lesson_plan_query().where(
                LessonPlanRecord.learner_id == learner_id,
                LessonPlanRecord.topic == topic,
                LessonPlanRecord.status == "active",
            )
        ).scalar_one_or_none()
        return _lesson_plan_from_record(record) if record is not None else None

    def supersede_active(self, learner_id: str, topic: str) -> None:
        records = self.db.execute(
            select(LessonPlanRecord).where(
                LessonPlanRecord.learner_id == learner_id,
                LessonPlanRecord.topic == topic,
                LessonPlanRecord.status == "active",
            )
        ).scalars().all()
        for record in records:
            record.status = "superseded"
            self.db.add(record)
        if records:
            self.db.commit()

    def save(self, lesson_plan: LessonPlan) -> LessonPlan:
        record = self.db.get(LessonPlanRecord, lesson_plan.id)
        if record is None:
            record = LessonPlanRecord(
                id=lesson_plan.id,
                learner_id=lesson_plan.learner_id,
                topic=lesson_plan.topic,
                status=lesson_plan.status,
                summary=lesson_plan.summary,
                current_step_index=lesson_plan.current_step_index,
                completed_step_ids=list(lesson_plan.completed_step_ids),
                trace=lesson_plan.trace.model_dump(mode="json") if lesson_plan.trace else None,
                created_at=lesson_plan.created_at,
                updated_at=lesson_plan.updated_at,
            )
        else:
            record.status = lesson_plan.status
            record.summary = lesson_plan.summary
            record.current_step_index = lesson_plan.current_step_index
            record.completed_step_ids = list(lesson_plan.completed_step_ids)
            record.trace = lesson_plan.trace.model_dump(mode="json") if lesson_plan.trace else None
            record.updated_at = lesson_plan.updated_at
            record.steps.clear()
            self.db.flush()

        record.steps.extend(
            [
                LessonPlanStepRecord(
                    id=step.id,
                    position=index,
                    title=step.title,
                    objective_id=step.objective_id,
                    objective_slug=step.objective_slug,
                    instruction=step.instruction,
                    rationale=step.rationale,
                    step_type=step.step_type,
                )
                for index, step in enumerate(lesson_plan.steps)
            ]
        )
        self.db.add(record)
        self.db.commit()
        refreshed = self.db.execute(_lesson_plan_query().where(LessonPlanRecord.id == lesson_plan.id)).scalar_one()
        return _lesson_plan_from_record(refreshed)


class SqlAccountRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def create(self, account: Account, password_hash: str) -> Account:
        record = AccountRecord(
            id=account.id,
            email=account.email,
            password_hash=password_hash,
            learner_id=account.learner_id,
            created_at=account.created_at,
        )
        self.db.add(record)
        self.db.commit()
        return _account_from_record(record)

    def get_by_email(self, email: str) -> tuple[Account, str] | None:
        record = self.db.execute(select(AccountRecord).where(AccountRecord.email == email)).scalar_one_or_none()
        if record is None:
            return None
        return _account_from_record(record), record.password_hash

    def get(self, account_id: str) -> Account | None:
        record = self.db.get(AccountRecord, account_id)
        return _account_from_record(record) if record is not None else None

    def create_session(self, auth_session: AuthSession, token_hash: str) -> AuthSession:
        record = AuthSessionRecord(
            id=auth_session.id,
            account_id=auth_session.account_id,
            token_hash=token_hash,
            expires_at=auth_session.expires_at,
            status=auth_session.status.value,
            created_at=auth_session.created_at,
        )
        self.db.add(record)
        self.db.commit()
        return _auth_session_from_record(record)

    def get_session(self, token_hash: str) -> AuthSession | None:
        record = self.db.execute(
            select(AuthSessionRecord).where(AuthSessionRecord.token_hash == token_hash)
        ).scalar_one_or_none()
        return _auth_session_from_record(record) if record is not None else None

    def revoke_session(self, token_hash: str) -> None:
        record = self.db.execute(
            select(AuthSessionRecord).where(AuthSessionRecord.token_hash == token_hash)
        ).scalar_one_or_none()
        if record is None:
            return
        record.status = AuthSessionStatus.REVOKED.value
        self.db.add(record)
        self.db.commit()
