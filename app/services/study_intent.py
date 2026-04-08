from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.models.api import CreateSessionRequest
from app.models.domain import Concept, GenerationTrace, Learner, LessonPlan, Session, utc_now
from app.services.lesson_planner import LessonPlannerService
from app.services.llm import LlmProvider
from app.services.objectives import ObjectiveGenerator
from app.services.repositories import CurriculumRepository, LearnerRepository, SessionRepository


class StudyIntentPayload(BaseModel):
    topic_slug: str
    topic_title: str
    subject: str
    description: str
    objective_titles: list[str] = Field(min_length=3, max_length=5)


class StudyIntentService:
    PROMPT_VERSION = "study_intent_v2"

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
            "<task>\n"
            "Interpret what the learner wants to study today and turn it into one teachable course topic.\n"
            "Prefer a scoped, lesson-sized topic over a giant field when the request is broad.\n"
            "</task>\n\n"
            f"<learner_context>\n"
            f"prior_goal: {learner.goal}\n"
            f"request_for_today: {prompt}\n"
            f"teaching_style: {learner.learning_style.teaching_style}\n"
            f"prefers_examples: {learner.learning_style.prefers_examples}\n"
            f"</learner_context>\n\n"
            "<requirements>\n"
            "- Infer exactly one teachable topic.\n"
            "- Make the description specific enough to guide lesson generation.\n"
            "- Write 3 to 5 concrete objectives that could appear in a real course outline.\n"
            "- The topic slug must be lowercase and hyphenated.\n"
            "- If the learner request is broad, choose the best first slice rather than mirroring the whole field.\n"
            "</requirements>"
        )
        instructions = (
            "You are a curriculum intake parser for an AI tutor.\n"
            "Return only JSON matching the schema.\n"
            "Be concrete and scope intelligently.\n"
            "Avoid vague objectives like 'understand better' or 'learn basics' unless refined."
        )
        payload = self.llm_provider.generate_structured(
            prompt=request,
            schema=StudyIntentPayload,
            schema_name="study_intent",
            instructions=instructions,
        )
        payload.topic_slug = _slugify(payload.topic_slug or payload.topic_title or prompt)
        trace = GenerationTrace(
            provider=self.llm_provider.provider_name,
            model=self.llm_provider.model_name,
            prompt_version=self.PROMPT_VERSION,
            prompt_inputs=prompt_inputs,
        )
        return payload, trace


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "custom-topic"
