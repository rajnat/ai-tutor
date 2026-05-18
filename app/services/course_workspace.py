from __future__ import annotations

import re
from datetime import UTC, datetime

from app.models.domain import (
    CheckpointAttempt,
    Concept,
    Course,
    CourseSection,
    CourseSectionContent,
    CourseSectionStatus,
    Learner,
    LessonPlan,
    LessonPlanStep,
    Session,
)
from app.services.lesson_content import LessonContentService
from app.services.repositories import CourseRepository, LessonPlanRepository


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


class CourseWorkspaceService:
    def __init__(
        self,
        course_repository: CourseRepository,
        lesson_plan_repository: LessonPlanRepository,
        lesson_content_service: LessonContentService,
    ) -> None:
        self.course_repository = course_repository
        self.lesson_plan_repository = lesson_plan_repository
        self.lesson_content_service = lesson_content_service

    def ensure_course(
        self,
        *,
        learner: Learner,
        concept: Concept,
        lesson_plan: LessonPlan,
    ) -> Course:
        existing = self.course_repository.get_active(learner.id, concept.slug)
        if existing is None:
            course = Course(
                learner_id=learner.id,
                title=concept.title,
                study_prompt=learner.goal,
                topic_slug=concept.slug,
                subject=concept.subject,
            )
        else:
            course = existing.model_copy(deep=True)
            course.title = concept.title
            course.study_prompt = learner.goal
            course.topic_slug = concept.slug
            course.subject = concept.subject

        active_step_id = None
        if lesson_plan.steps:
            active_index = min(max(lesson_plan.current_step_index, 0), len(lesson_plan.steps) - 1)
            active_step_id = lesson_plan.steps[active_index].id

        existing_sections_by_position = {section.position: section for section in course.sections}
        synced_sections: list[CourseSection] = []
        for position, step in enumerate(lesson_plan.steps):
            existing_section = existing_sections_by_position.get(position)
            status = CourseSectionStatus.AVAILABLE
            if step.id in lesson_plan.completed_step_ids:
                status = CourseSectionStatus.COMPLETED
            elif step.id == active_step_id:
                status = CourseSectionStatus.ACTIVE

            synced_sections.append(
                CourseSection(
                    id=existing_section.id if existing_section is not None else CourseSection(course_id=course.id, position=position, title=step.title, slug=_slugify(step.title), summary=step.instruction).id,
                    course_id=course.id,
                    position=position,
                    title=step.title,
                    slug=_slugify(step.title),
                    summary=step.instruction,
                    objective_ids=[step.objective_id] if step.objective_id is not None else [],
                    status=status,
                )
            )

        course.sections = synced_sections
        course.current_section_id = next(
            (section.id for section in course.sections if section.status == CourseSectionStatus.ACTIVE),
            course.sections[0].id if course.sections else None,
        )
        course.updated_at = datetime.now(UTC)
        return self.course_repository.save(course)

    def current_section(self, course: Course) -> CourseSection | None:
        if not course.sections:
            return None
        if course.current_section_id is not None:
            for section in course.sections:
                if section.id == course.current_section_id:
                    return section
        return course.sections[0]

    def get_or_create_section_content(
        self,
        *,
        course: Course,
        section: CourseSection,
        learner: Learner,
        concept: Concept,
        lesson_plan: LessonPlan,
        active_step: LessonPlanStep | None,
        recent_messages: list[str],
        force_regenerate: bool = False,
        prior_wrong_answer: str | None = None,
        prior_checkpoint_explanation: str | None = None,
    ) -> CourseSectionContent:
        existing = self.course_repository.get_section_content(course.id, section.id)
        if existing is not None and not force_regenerate:
            return existing

        content = self.lesson_content_service.generate(
            learner=learner,
            concept=concept,
            lesson_plan=lesson_plan,
            active_step=active_step,
            recent_messages=recent_messages,
            prior_wrong_answer=prior_wrong_answer,
            prior_checkpoint_explanation=prior_checkpoint_explanation,
        )
        record = CourseSectionContent(
            course_id=course.id,
            section_id=section.id,
            content=content,
        )
        # Preserve the id if we're replacing existing content so foreign keys stay stable.
        if existing is not None:
            record = CourseSectionContent(
                id=existing.id,
                course_id=course.id,
                section_id=section.id,
                content=content,
            )
        return self.course_repository.save_section_content(record)

    def record_checkpoint_attempt(
        self,
        *,
        learner_id: str,
        course_id: str,
        session_id: str,
        checkpoint_id: str,
        selected_option_id: str,
        is_correct: bool,
        explanation: str,
    ) -> CheckpointAttempt:
        return self.course_repository.create_checkpoint_attempt(
            CheckpointAttempt(
                learner_id=learner_id,
                course_id=course_id,
                session_id=session_id,
                checkpoint_id=checkpoint_id,
                selected_option_id=selected_option_id,
                is_correct=is_correct,
                explanation=explanation,
            )
        )

    def activate_section(
        self,
        *,
        course: Course,
        lesson_plan: LessonPlan,
        section_id: str,
    ) -> tuple[Course, LessonPlan]:
        section = next((item for item in course.sections if item.id == section_id), None)
        if section is None:
            raise ValueError(f"Section {section_id} not found")

        for item in course.sections:
            if item.id == section_id:
                item.status = CourseSectionStatus.ACTIVE
            elif item.status != CourseSectionStatus.COMPLETED:
                item.status = CourseSectionStatus.AVAILABLE
        course.current_section_id = section.id
        course.updated_at = datetime.now(UTC)
        saved_course = self.course_repository.save(course)

        lesson_plan.current_step_index = min(max(section.position, 0), max(len(lesson_plan.steps) - 1, 0))
        lesson_plan.updated_at = datetime.now(UTC)
        saved_plan = self.lesson_plan_repository.save(lesson_plan)
        return saved_course, saved_plan

    def advance_after_checkpoint(
        self,
        *,
        course: Course,
        lesson_plan: LessonPlan,
        is_correct: bool,
    ) -> tuple[Course, LessonPlan]:
        current_section = self.current_section(course)
        if current_section is None:
            return course, lesson_plan

        if not is_correct:
            return course, lesson_plan

        if current_section.position < len(lesson_plan.steps):
            current_step = lesson_plan.steps[current_section.position]
            if current_step.id not in lesson_plan.completed_step_ids:
                lesson_plan.completed_step_ids.append(current_step.id)

        next_index = min(current_section.position + 1, max(len(course.sections) - 1, 0))
        next_section = course.sections[next_index] if course.sections else None

        for item in course.sections:
            if item.id == current_section.id:
                item.status = CourseSectionStatus.COMPLETED
            elif next_section is not None and item.id == next_section.id:
                item.status = CourseSectionStatus.ACTIVE
            elif item.status != CourseSectionStatus.COMPLETED:
                item.status = CourseSectionStatus.AVAILABLE

        course.current_section_id = next_section.id if next_section is not None else current_section.id
        course.updated_at = datetime.now(UTC)
        saved_course = self.course_repository.save(course)

        lesson_plan.current_step_index = next_index
        lesson_plan.updated_at = datetime.now(UTC)
        saved_plan = self.lesson_plan_repository.save(lesson_plan)
        return saved_course, saved_plan
