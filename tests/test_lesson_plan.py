from app.models.domain import Concept, ConceptObjective, ContentSnippet, Learner, LearningPreferences
from app.services.lesson_planner import LessonPlannerService


class InMemoryLessonPlanRepository:
    def __init__(self) -> None:
        self.plan = None

    def get_active(self, learner_id: str, topic: str):
        if self.plan and self.plan.learner_id == learner_id and self.plan.topic == topic and self.plan.status == "active":
            return self.plan
        return None

    def supersede_active(self, learner_id: str, topic: str) -> None:
        if self.plan and self.plan.learner_id == learner_id and self.plan.topic == topic:
            self.plan.status = "superseded"

    def save(self, lesson_plan):
        self.plan = lesson_plan
        return lesson_plan


class StubPlannerProvider:
    provider_name = "stub"
    model_name = "stub-model"

    def generate_structured(self, prompt: str, schema: type, schema_name: str, instructions: str = ""):
        assert schema_name == "lesson_plan"
        return schema.model_validate(
            {
                "summary": "A simple lesson plan.",
                "steps": [
                    {
                        "title": "Build intuition",
                        "objective_id": "obj-1",
                        "objective_slug": "algebra:intuition",
                        "instruction": "Explain the core idea plainly.",
                        "rationale": "Intuition comes first.",
                        "step_type": "explain",
                    },
                    {
                        "title": "Check understanding",
                        "objective_id": "obj-1",
                        "objective_slug": "algebra:intuition",
                        "instruction": "Ask one focused question.",
                        "rationale": "Confirm understanding.",
                        "step_type": "diagnostic",
                    },
                    {
                        "title": "Apply it",
                        "objective_id": "obj-2",
                        "objective_slug": "algebra:application",
                        "instruction": "Work one short example.",
                        "rationale": "Application stabilizes learning.",
                        "step_type": "practice",
                    },
                ],
            }
        )


def test_lesson_planner_creates_persisted_plan() -> None:
    repository = InMemoryLessonPlanRepository()
    planner = LessonPlannerService(repository, StubPlannerProvider())

    learner = Learner(name="Eswar", goal="Learn algebra", learning_style=LearningPreferences())
    concept = Concept(
        slug="algebra",
        title="Algebra Foundations",
        description="Core algebraic manipulation.",
        subject="math",
        objectives=[
            ConceptObjective(
                id="obj-1",
                slug="algebra:intuition",
                title="Conceptual intuition",
                description="Understand the core idea.",
            ),
            ConceptObjective(
                id="obj-2",
                slug="algebra:application",
                title="Basic application",
                description="Apply the idea correctly.",
            ),
        ],
    )
    snippets = [
        ContentSnippet(
            id="content-1",
            title="Notation overview",
            topic_slug="algebra",
            objective_slugs=["algebra:intuition"],
            content_type="overview",
            difficulty="beginner",
            source_name="Seed Library",
            summary="Overview summary",
            text="Overview text",
        )
    ]

    plan = planner.get_or_create_plan(learner, concept, snippets)
    assert plan.summary == "A simple lesson plan."
    assert len(plan.steps) == 3
    assert plan.trace is not None
    assert plan.trace.prompt_version == "lesson_plan_v3"


def test_lesson_planner_advances_progress() -> None:
    repository = InMemoryLessonPlanRepository()
    planner = LessonPlannerService(repository, StubPlannerProvider())

    learner = Learner(name="Eswar", goal="Learn algebra", learning_style=LearningPreferences())
    concept = Concept(
        slug="algebra",
        title="Algebra Foundations",
        description="Core algebraic manipulation.",
        subject="math",
        objectives=[
            ConceptObjective(
                id="obj-1",
                slug="algebra:intuition",
                title="Conceptual intuition",
                description="Understand the core idea.",
            ),
        ],
    )

    plan = planner.create_plan(learner, concept, [])
    # High-correctness response on an objective-focused step should complete it.
    updated = planner.advance_progress(
        plan,
        action="ask_diagnostic",
        correctness=0.8,
        focus_objective_id="obj-1",
        topic_ready_to_advance=False,
    )

    assert len(updated.completed_step_ids) >= 1
    assert updated.current_step_index >= 1


def test_lesson_progress_persists_across_sessions() -> None:
    """Progress saved in one session must be visible when the plan is reloaded."""
    repository = InMemoryLessonPlanRepository()
    planner = LessonPlannerService(repository, StubPlannerProvider())

    learner = Learner(name="Eswar", goal="Learn algebra", learning_style=LearningPreferences())
    concept = Concept(
        slug="algebra",
        title="Algebra Foundations",
        description="Core algebraic manipulation.",
        subject="math",
        objectives=[
            ConceptObjective(
                id="obj-1",
                slug="algebra:intuition",
                title="Conceptual intuition",
                description="Understand the core idea.",
            ),
        ],
    )

    # Session 1: create plan and advance one step.
    plan = planner.create_plan(learner, concept, [])
    assert plan.current_step_index == 0

    planner.advance_progress(
        plan,
        action="ask_diagnostic",
        correctness=0.9,
        focus_objective_id="obj-1",
        topic_ready_to_advance=False,
    )

    # Session 2: reload from the repository — progress must survive.
    reloaded = planner.get_or_create_plan(learner, concept, [])
    assert reloaded.current_step_index >= 1, "step index not persisted across sessions"
    assert len(reloaded.completed_step_ids) >= 1, "completed_step_ids not persisted across sessions"

    # The reloaded plan's current step must not be in completed_step_ids.
    current_step = reloaded.steps[reloaded.current_step_index]
    assert current_step.id not in reloaded.completed_step_ids, "current step should not be marked complete"
