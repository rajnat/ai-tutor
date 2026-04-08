from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.models.api import CreateSessionRequest
from app.models.domain import Concept, GenerationTrace, Learner, LessonPlan, Session, utc_now
from app.services.lesson_planner import LessonPlannerService
from app.services.llm import LlmError, LlmProvider
from app.services.objectives import ObjectiveGenerator
from app.services.repositories import CurriculumRepository, LearnerRepository, SessionRepository


class StudyIntentPayload(BaseModel):
    topic_slug: str
    topic_title: str
    subject: str
    description: str
    objective_titles: list[str] = Field(min_length=3, max_length=5)


class StudyIntentService:
    PROMPT_VERSION = "study_intent_v1"
    FALLBACK_PROMPT_VERSION = "study_intent_fallback_v1"

    def __init__(
        self,
        curriculum_repository: CurriculumRepository,
        learner_repository: LearnerRepository,
        session_repository: SessionRepository,
        lesson_planner: LessonPlannerService,
        llm_provider: LlmProvider,
    ) -> None:
        self.curriculum_repository = curriculum_repository
        self.learner_repository = learner_repository
        self.session_repository = session_repository
        self.lesson_planner = lesson_planner
        self.llm_provider = llm_provider
        self.objective_generator = ObjectiveGenerator()
        self.logger = logging.getLogger(__name__)

    def launch(
        self,
        *,
        learner: Learner,
        prompt: str,
        mode: str = "learn",
    ) -> tuple[Learner, Concept, LessonPlan, Session]:
        payload, _trace = self._generate_intent(learner, prompt)
        concept = self.curriculum_repository.get_by_slug(payload.topic_slug)
        if concept is None:
            concept = self.curriculum_repository.create_concept(
                Concept(
                    slug=payload.topic_slug,
                    title=payload.topic_title,
                    description=payload.description,
                    subject=payload.subject,
                    prerequisites=[],
                    objectives=self.objective_generator.infer_objectives(
                        concept_slug=payload.topic_slug,
                        concept_description=payload.description,
                        objective_titles=payload.objective_titles,
                    ),
                )
            )

        updated_learner = learner.model_copy(deep=True)
        updated_learner.goal = prompt.strip()
        updated_learner.updated_at = utc_now()
        saved_learner = self.learner_repository.save(updated_learner)
        lesson_plan = self.lesson_planner.create_plan(saved_learner, concept, [])
        session = self.session_repository.create(
            CreateSessionRequest(
                learner_id=saved_learner.id,
                topic=concept.slug,
                mode=mode,
            )
        )
        return saved_learner, concept, lesson_plan, session

    def _generate_intent(self, learner: Learner, prompt: str) -> tuple[StudyIntentPayload, GenerationTrace]:
        prompt_inputs = {
            "learner_id": learner.id,
            "prompt": prompt,
        }
        request = (
            "You are planning the first lesson for an adaptive AI tutor.\n"
            "Return JSON only.\n"
            "Infer a single teachable topic from the learner request.\n"
            "Write a concise description and 3 to 5 concrete lesson objectives.\n"
            "The topic slug must be short, lowercase, and hyphenated.\n\n"
            f"Learner goal history: {learner.goal}\n"
            f"Learner request for today: {prompt}\n"
            f"Learner teaching style: {learner.learning_style.teaching_style}\n"
            f"Learner prefers examples: {learner.learning_style.prefers_examples}\n"
        )
        try:
            payload = self.llm_provider.generate_structured(
                prompt=request,
                schema=StudyIntentPayload,
                schema_name="study_intent",
            )
            payload.topic_slug = _slugify(payload.topic_slug or payload.topic_title or prompt)
            trace = GenerationTrace(
                provider=self.llm_provider.provider_name,
                model=self.llm_provider.model_name,
                prompt_version=self.PROMPT_VERSION,
                prompt_inputs=prompt_inputs,
            )
            return payload, trace
        except LlmError as error:
            self.logger.warning(
                "Falling back to deterministic study intent learner_id=%s prompt=%s error_type=%s",
                learner.id,
                prompt,
                type(error).__name__,
            )
            fallback = _fallback_payload(prompt)
            trace = GenerationTrace(
                provider="system",
                model="fallback",
                prompt_version=self.FALLBACK_PROMPT_VERSION,
                prompt_inputs={**prompt_inputs, "error_type": type(error).__name__},
            )
            return fallback, trace


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "custom-topic"


def _fallback_payload(prompt: str) -> StudyIntentPayload:
    normalized = prompt.strip()
    title = normalized[:80].strip().rstrip(".?!") or "Custom Topic"
    return StudyIntentPayload(
        topic_slug=_slugify(title),
        topic_title=title.title(),
        subject="general",
        description=f"A focused lesson on {title.lower()} tailored to the learner's request.",
        objective_titles=[
            "Core intuition",
            "Key vocabulary",
            "Basic application",
            "Check understanding",
        ],
    )
