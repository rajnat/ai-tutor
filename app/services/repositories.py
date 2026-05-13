from __future__ import annotations

from typing import Protocol

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session as DbSession, selectinload

from app.models.api import CreateLearnerRequest, CreateSessionRequest
from app.services.tutor_config import DEFAULT_CONFIG
from app.models.domain import (
    Account,
    AuthSession,
    AuthSessionStatus,
    CheckpointAttempt,
    Concept,
    ConceptObjective,
    Course,
    CourseSection,
    CourseSectionContent,
    CourseSectionStatus,
    CourseStatus,
    EvaluationResult,
    GenerationTrace,
    Learner,
    LearningPreferences,
    LessonPlan,
    LessonPlanStep,
    LessonSectionContent,
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
    CheckpointAttemptRecord,
    ConceptObjectiveRecord,
    ConceptPrerequisiteRecord,
    ConceptRecord,
    CourseRecord,
    CourseSectionContentRecord,
    CourseSectionRecord,
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


class CourseRepository(Protocol):
    def get_active(self, learner_id: str, topic_slug: str) -> Course | None: ...
    def save(self, course: Course) -> Course: ...
    def get_section_content(self, course_id: str, section_id: str) -> CourseSectionContent | None: ...
    def save_section_content(self, section_content: CourseSectionContent) -> CourseSectionContent: ...
    def create_checkpoint_attempt(self, attempt: CheckpointAttempt) -> CheckpointAttempt: ...


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
        prompt=record.prompt,
        objective_id=record.objective_id,
        objective_slug=record.objective_slug,
        expected_answer=record.expected_answer,
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
        is_admin=record.is_admin,
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


def _course_from_record(record: CourseRecord) -> Course:
    return Course(
        id=record.id,
        learner_id=record.learner_id,
        title=record.title,
        study_prompt=record.study_prompt,
        topic_slug=record.topic_slug,
        subject=record.subject,
        status=CourseStatus(record.status),
        current_section_id=record.current_section_id,
        sections=[
            CourseSection(
                id=section.id,
                course_id=section.course_id,
                position=section.position,
                title=section.title,
                slug=section.slug,
                summary=section.summary,
                objective_ids=list(section.objective_ids or []),
                status=CourseSectionStatus(section.status),
            )
            for section in record.sections
        ],
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _course_section_content_from_record(record: CourseSectionContentRecord) -> CourseSectionContent:
    return CourseSectionContent(
        id=record.id,
        course_id=record.course_id,
        section_id=record.section_id,
        content=LessonSectionContent.model_validate(record.content),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _checkpoint_attempt_from_record(record: CheckpointAttemptRecord) -> CheckpointAttempt:
    return CheckpointAttempt(
        id=record.id,
        learner_id=record.learner_id,
        course_id=record.course_id,
        session_id=record.session_id,
        checkpoint_id=record.checkpoint_id,
        selected_option_id=record.selected_option_id,
        is_correct=record.is_correct,
        explanation=record.explanation,
        created_at=record.created_at,
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


def _course_query():
    return select(CourseRecord).options(selectinload(CourseRecord.sections))


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
            learner.skills[payload.initial_topic] = TopicState(
                mastery=DEFAULT_CONFIG.initial_known_topic_mastery,
                confidence=DEFAULT_CONFIG.initial_known_topic_confidence,
            )

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

        # Bulk-delete all child rows first, then insert the new set in one
        # commit.  This avoids two failure modes that the old clear()/flush()
        # pattern had:
        #
        # 1. An exception during an intermediate flush left child collections
        #    partially deleted with no new rows inserted yet.
        # 2. Re-saving a topic/objective that already exists hit the unique
        #    constraint because the ORM could INSERT before the DELETE.
        #
        # execute(delete()) runs the SQL immediately within the current
        # transaction, guaranteeing all DELETEs precede any INSERTs.
        self.db.execute(
            sa_delete(LearnerTopicStateRecord).where(LearnerTopicStateRecord.learner_id == learner.id)
        )
        self.db.execute(
            sa_delete(LearnerObjectiveStateRecord).where(LearnerObjectiveStateRecord.learner_id == learner.id)
        )
        self.db.execute(
            sa_delete(LearnerMisconceptionRecord).where(LearnerMisconceptionRecord.learner_id == learner.id)
        )
        # Expire the cached relationship lists so SQLAlchemy reloads them from
        # the database instead of serving stale in-memory objects.
        self.db.expire(record, ["topic_states", "objective_states", "misconceptions"])

        for topic, state in learner.skills.items():
            self.db.add(LearnerTopicStateRecord(
                learner_id=learner.id,
                topic=topic,
                mastery=state.mastery,
                confidence=state.confidence,
                last_practiced_at=state.last_practiced_at,
            ))
        for objective_id, state in learner.objective_states.items():
            self.db.add(LearnerObjectiveStateRecord(
                learner_id=learner.id,
                objective_id=objective_id,
                mastery=state.mastery,
                confidence=state.confidence,
                last_practiced_at=state.last_practiced_at,
            ))
        for item in learner.misconceptions:
            self.db.add(LearnerMisconceptionRecord(
                learner_id=learner.id,
                topic=item.topic,
                description=item.description,
                severity=item.severity,
                created_at=item.created_at,
            ))

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
                prompt=review_item.prompt,
                objective_id=review_item.objective_id,
                objective_slug=review_item.objective_slug,
                expected_answer=review_item.expected_answer,
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
            record.prompt = review_item.prompt
            record.objective_id = review_item.objective_id
            record.objective_slug = review_item.objective_slug
            record.expected_answer = review_item.expected_answer
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


class SqlCourseRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def get_active(self, learner_id: str, topic_slug: str) -> Course | None:
        record = self.db.execute(
            _course_query()
            .where(
                CourseRecord.learner_id == learner_id,
                CourseRecord.topic_slug == topic_slug,
                CourseRecord.status == CourseStatus.ACTIVE.value,
            )
            .order_by(CourseRecord.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return _course_from_record(record) if record is not None else None

    def save(self, course: Course) -> Course:
        record = self.db.get(CourseRecord, course.id)
        if record is None:
            record = CourseRecord(
                id=course.id,
                learner_id=course.learner_id,
                title=course.title,
                study_prompt=course.study_prompt,
                topic_slug=course.topic_slug,
                subject=course.subject,
                status=course.status.value,
                current_section_id=course.current_section_id,
                created_at=course.created_at,
                updated_at=course.updated_at,
            )
            record.sections = [
                CourseSectionRecord(
                    id=section.id,
                    position=section.position,
                    title=section.title,
                    slug=section.slug,
                    summary=section.summary,
                    objective_ids=list(section.objective_ids),
                    status=section.status.value,
                )
                for section in course.sections
            ]
        else:
            record.title = course.title
            record.study_prompt = course.study_prompt
            record.topic_slug = course.topic_slug
            record.subject = course.subject
            record.status = course.status.value
            record.current_section_id = course.current_section_id
            record.updated_at = course.updated_at
            existing_sections_by_id = {section.id: section for section in record.sections}
            desired_ids = {section.id for section in course.sections}
            for section_record in list(record.sections):
                if section_record.id not in desired_ids:
                    record.sections.remove(section_record)
                    self.db.delete(section_record)
            for section in course.sections:
                section_record = existing_sections_by_id.get(section.id)
                if section_record is None:
                    record.sections.append(
                        CourseSectionRecord(
                            id=section.id,
                            position=section.position,
                            title=section.title,
                            slug=section.slug,
                            summary=section.summary,
                            objective_ids=list(section.objective_ids),
                            status=section.status.value,
                        )
                    )
                else:
                    section_record.position = section.position
                    section_record.title = section.title
                    section_record.slug = section.slug
                    section_record.summary = section.summary
                    section_record.objective_ids = list(section.objective_ids)
                    section_record.status = section.status.value
        self.db.add(record)
        self.db.commit()
        refreshed = self.db.execute(_course_query().where(CourseRecord.id == course.id)).scalar_one()
        return _course_from_record(refreshed)

    def get_section_content(self, course_id: str, section_id: str) -> CourseSectionContent | None:
        record = self.db.execute(
            select(CourseSectionContentRecord).where(
                CourseSectionContentRecord.course_id == course_id,
                CourseSectionContentRecord.section_id == section_id,
            )
        ).scalar_one_or_none()
        return _course_section_content_from_record(record) if record is not None else None

    def save_section_content(self, section_content: CourseSectionContent) -> CourseSectionContent:
        record = self.db.get(CourseSectionContentRecord, section_content.id)
        if record is None:
            record = CourseSectionContentRecord(
                id=section_content.id,
                course_id=section_content.course_id,
                section_id=section_content.section_id,
                content=section_content.content.model_dump(mode="json"),
                created_at=section_content.created_at,
                updated_at=section_content.updated_at,
            )
        else:
            record.content = section_content.content.model_dump(mode="json")
            record.updated_at = section_content.updated_at

        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return _course_section_content_from_record(record)

    def create_checkpoint_attempt(self, attempt: CheckpointAttempt) -> CheckpointAttempt:
        record = CheckpointAttemptRecord(
            id=attempt.id,
            learner_id=attempt.learner_id,
            course_id=attempt.course_id,
            session_id=attempt.session_id,
            checkpoint_id=attempt.checkpoint_id,
            selected_option_id=attempt.selected_option_id,
            is_correct=attempt.is_correct,
            explanation=attempt.explanation,
            created_at=attempt.created_at,
        )
        self.db.add(record)
        self.db.commit()
        return _checkpoint_attempt_from_record(record)


class SqlAccountRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def create(self, account: Account, password_hash: str) -> Account:
        record = AccountRecord(
            id=account.id,
            email=account.email,
            password_hash=password_hash,
            learner_id=account.learner_id,
            is_admin=account.is_admin,
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
