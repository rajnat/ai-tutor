from datetime import UTC, datetime, timedelta

from app.models.domain import Concept, ConceptObjective, ReviewItem, ReviewStatus
from app.services.tutor_config import DEFAULT_CONFIG, TutorConfig


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_aware(dt: datetime) -> datetime:
    """Return dt as a timezone-aware UTC datetime.

    SQLite may return naive datetimes even from DateTime(timezone=True) columns;
    treat any naive value as UTC so comparisons don't raise TypeError.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class ReviewScheduler:
    def __init__(self, config: TutorConfig = DEFAULT_CONFIG) -> None:
        self.config = config

    def build_review_prompt(
        self,
        *,
        topic: str,
        concept: Concept | None,
        focus_objective: ConceptObjective | None,
    ) -> tuple[str, str | None]:
        concept_title = concept.title if concept is not None else topic
        if focus_objective is None:
            return (
                f"In your own words, what is the central idea in {concept_title}, and why does it matter?",
                concept.description if concept is not None else None,
            )

        objective_text = f"{focus_objective.slug} {focus_objective.title} {focus_objective.description}".lower()
        if "notation" in objective_text or "vocabulary" in objective_text:
            prompt = (
                f"What does {focus_objective.title.lower()} mean in {concept_title}? "
                "Answer in plain language and define one important symbol or term."
            )
        elif "application" in objective_text or "solve" in objective_text or "practice" in objective_text:
            prompt = (
                f"Give one short example that demonstrates {focus_objective.title.lower()} in {concept_title}, "
                "then explain why it works."
            )
        elif "compare" in objective_text or "transfer" in objective_text:
            prompt = (
                f"Compare two cases or examples that highlight {focus_objective.title.lower()} in {concept_title}. "
                "What changes and what stays the same?"
            )
        else:
            prompt = (
                f"Explain {focus_objective.title.lower()} in {concept_title} in your own words, "
                "using one example if it helps."
            )
        return prompt, focus_objective.description

    def schedule_after_turn(
        self,
        learner_id: str,
        topic: str,
        correctness: float,
        existing: ReviewItem | None,
        concept: Concept | None = None,
        focus_objective: ConceptObjective | None = None,
    ) -> ReviewItem:
        cfg = self.config
        now = utc_now()
        interval_days = (
            1 if correctness < cfg.review_short_interval_boundary
            else 3 if correctness < cfg.review_medium_interval_boundary
            else 7
        )
        due_at = now if correctness < cfg.review_short_interval_boundary else now + timedelta(days=interval_days)
        status = ReviewStatus.DUE if due_at <= now else ReviewStatus.SCHEDULED
        prompt, expected_answer = self.build_review_prompt(
            topic=topic,
            concept=concept,
            focus_objective=focus_objective,
        )

        if existing is None:
            return ReviewItem(
                learner_id=learner_id,
                topic=topic,
                prompt=prompt,
                objective_id=focus_objective.id if focus_objective is not None else None,
                objective_slug=focus_objective.slug if focus_objective is not None else None,
                expected_answer=expected_answer,
                due_at=due_at,
                status=status,
                interval_days=interval_days,
            )

        # Always refresh the prompt and objective focus so it tracks the current weak area.
        existing.prompt = prompt
        existing.objective_id = focus_objective.id if focus_objective is not None else None
        existing.objective_slug = focus_objective.slug if focus_objective is not None else None
        existing.expected_answer = expected_answer
        existing.updated_at = now

        # Only pull the schedule forward if the item is already due/overdue, or the new
        # due date would be sooner than what's already scheduled.  Never push a future
        # interval further out: that would stomp the exponential backoff earned via
        # complete_review and keep reviews perpetually deferred.
        existing_due_at = _as_aware(existing.due_at)
        if existing.status == ReviewStatus.DUE or existing_due_at <= now or due_at < existing_due_at:
            existing.due_at = due_at
            existing.status = status
            existing.interval_days = interval_days

        return existing

    def complete_review(self, review_item: ReviewItem, correctness: float) -> ReviewItem:
        cfg = self.config
        now = utc_now()
        next_interval = (
            max(review_item.interval_days + 1, review_item.interval_days * 2)
            if correctness >= cfg.review_double_interval_threshold
            else max(2, review_item.interval_days + 1)
            if correctness >= cfg.review_grow_interval_threshold
            else 1
        )
        review_item.review_count += 1
        review_item.last_reviewed_at = now
        review_item.interval_days = next_interval
        review_item.due_at = now + timedelta(days=next_interval)
        review_item.status = ReviewStatus.SCHEDULED if correctness >= cfg.review_reschedule_threshold else ReviewStatus.DUE
        if correctness < cfg.review_reschedule_threshold:
            review_item.due_at = now
        review_item.updated_at = now
        return review_item
