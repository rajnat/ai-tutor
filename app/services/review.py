from datetime import UTC, datetime, timedelta

from app.models.domain import ReviewItem, ReviewStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class ReviewScheduler:
    def schedule_after_turn(
        self,
        learner_id: str,
        topic: str,
        correctness: float,
        existing: ReviewItem | None,
    ) -> ReviewItem:
        now = utc_now()
        interval_days = 1 if correctness < 0.5 else 3 if correctness < 0.75 else 7
        due_at = now if correctness < 0.5 else now + timedelta(days=interval_days)
        status = ReviewStatus.DUE if due_at <= now else ReviewStatus.SCHEDULED

        if existing is None:
            return ReviewItem(
                learner_id=learner_id,
                topic=topic,
                due_at=due_at,
                status=status,
                interval_days=interval_days,
            )

        existing.due_at = due_at
        existing.status = status
        existing.interval_days = interval_days
        existing.updated_at = now
        return existing

    def complete_review(self, review_item: ReviewItem, correct: bool) -> ReviewItem:
        now = utc_now()
        next_interval = max(1, review_item.interval_days * 2) if correct else 1
        review_item.review_count += 1
        review_item.last_reviewed_at = now
        review_item.interval_days = next_interval
        review_item.due_at = now + timedelta(days=next_interval)
        review_item.status = ReviewStatus.SCHEDULED
        review_item.updated_at = now
        return review_item
