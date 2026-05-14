from datetime import UTC, datetime, timedelta

from app.models.domain import Concept, ConceptObjective, ReviewItem, ReviewStatus
from app.services.review import ReviewScheduler


def _make_scheduled_review(*, days_from_now: float) -> ReviewItem:
    now = datetime.now(UTC)
    due_at = now + timedelta(days=days_from_now)
    return ReviewItem(
        learner_id="learner-1",
        topic="algebra",
        prompt="Existing prompt.",
        due_at=due_at,
        status=ReviewStatus.SCHEDULED,
        interval_days=7,
    )


def _make_due_review() -> ReviewItem:
    return ReviewItem(
        learner_id="learner-1",
        topic="algebra",
        prompt="Existing prompt.",
        due_at=datetime.now(UTC) - timedelta(hours=1),
        status=ReviewStatus.DUE,
        interval_days=1,
    )


_concept = Concept(
    slug="algebra",
    title="Algebra Foundations",
    description="Core algebraic manipulation.",
    subject="math",
)
_objective = ConceptObjective(
    id="obj-1",
    slug="algebra:notation",
    title="Notation",
    description="Use algebraic notation correctly.",
)


class TestScheduleAfterTurn:
    def test_creates_new_due_item_for_low_correctness(self) -> None:
        scheduler = ReviewScheduler()
        item = scheduler.schedule_after_turn(
            learner_id="learner-1",
            topic="algebra",
            correctness=0.2,
            existing=None,
            concept=_concept,
        )
        assert item.status == ReviewStatus.DUE
        assert item.interval_days == 1

    def test_creates_new_scheduled_item_for_high_correctness(self) -> None:
        scheduler = ReviewScheduler()
        item = scheduler.schedule_after_turn(
            learner_id="learner-1",
            topic="algebra",
            correctness=0.9,
            existing=None,
            concept=_concept,
        )
        assert item.status == ReviewStatus.SCHEDULED
        assert item.interval_days == 7
        assert item.due_at > datetime.now(UTC)

    def test_does_not_push_future_schedule_further_out(self) -> None:
        """A good session turn must not stomp an earned future interval."""
        scheduler = ReviewScheduler()
        existing = _make_scheduled_review(days_from_now=7)
        original_due_at = existing.due_at
        original_interval = existing.interval_days

        updated = scheduler.schedule_after_turn(
            learner_id="learner-1",
            topic="algebra",
            correctness=0.9,
            existing=existing,
            concept=_concept,
        )

        assert updated.due_at == original_due_at, "future due_at must not be overwritten by a good score"
        assert updated.interval_days == original_interval

    def test_pulls_schedule_forward_when_score_drops(self) -> None:
        """A bad score should move the review earlier, not defer it."""
        scheduler = ReviewScheduler()
        existing = _make_scheduled_review(days_from_now=7)

        updated = scheduler.schedule_after_turn(
            learner_id="learner-1",
            topic="algebra",
            correctness=0.2,
            existing=existing,
            concept=_concept,
        )

        assert updated.status == ReviewStatus.DUE
        assert updated.interval_days == 1

    def test_updates_prompt_and_objective_even_when_schedule_preserved(self) -> None:
        """Prompt refresh must happen even when due_at is not moved."""
        scheduler = ReviewScheduler()
        existing = _make_scheduled_review(days_from_now=7)
        assert existing.objective_id is None

        updated = scheduler.schedule_after_turn(
            learner_id="learner-1",
            topic="algebra",
            correctness=0.9,
            existing=existing,
            concept=_concept,
            focus_objective=_objective,
        )

        assert updated.objective_id == _objective.id
        assert updated.objective_slug == _objective.slug

    def test_reschedules_already_due_item(self) -> None:
        """A review already marked DUE should be rescheduled based on current score."""
        scheduler = ReviewScheduler()
        existing = _make_due_review()

        updated = scheduler.schedule_after_turn(
            learner_id="learner-1",
            topic="algebra",
            correctness=0.8,
            existing=existing,
            concept=_concept,
        )

        assert updated.interval_days == 7
        assert updated.due_at > datetime.now(UTC)


class TestCompleteReview:
    def test_doubles_interval_on_high_correctness(self) -> None:
        scheduler = ReviewScheduler()
        review = ReviewItem(
            learner_id="learner-1",
            topic="algebra",
            prompt="Explain the idea.",
            due_at=datetime.now(UTC),
            status=ReviewStatus.DUE,
            interval_days=4,
        )
        updated = scheduler.complete_review(review, correctness=0.95)
        assert updated.interval_days >= 8
        assert updated.status == ReviewStatus.SCHEDULED
        assert updated.review_count == 1

    def test_resets_interval_on_low_correctness(self) -> None:
        scheduler = ReviewScheduler()
        review = ReviewItem(
            learner_id="learner-1",
            topic="algebra",
            prompt="Explain the idea.",
            due_at=datetime.now(UTC),
            status=ReviewStatus.DUE,
            interval_days=14,
        )
        updated = scheduler.complete_review(review, correctness=0.3)
        assert updated.interval_days == 1
        assert updated.status == ReviewStatus.DUE


class TestPastDueSurfacing:
    """Verify that the scheduling logic produces items that the query would surface."""

    def test_overdue_scheduled_item_has_past_due_at(self) -> None:
        """An item scheduled in the past must have due_at <= now so the SQL query picks it up."""
        scheduler = ReviewScheduler()
        now = datetime.now(UTC)
        # Simulate a review scheduled 3 days ago that was never completed.
        existing = ReviewItem(
            learner_id="learner-1",
            topic="algebra",
            prompt="Old prompt.",
            due_at=now - timedelta(days=3),
            status=ReviewStatus.SCHEDULED,
            interval_days=3,
        )
        # A session turn today: does schedule_after_turn update this overdue item?
        updated = scheduler.schedule_after_turn(
            learner_id="learner-1",
            topic="algebra",
            correctness=0.9,
            existing=existing,
            concept=_concept,
        )
        # The item was overdue (due_at <= now), so the schedule should be refreshed.
        assert updated.due_at > now - timedelta(minutes=1), "overdue item should be rescheduled"
