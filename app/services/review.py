from datetime import UTC, datetime, timedelta

from app.models.domain import Concept, ConceptObjective, ReviewItem, ReviewStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class ReviewScheduler:
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
        now = utc_now()
        interval_days = 1 if correctness < 0.5 else 3 if correctness < 0.75 else 7
        due_at = now if correctness < 0.5 else now + timedelta(days=interval_days)
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

        existing.prompt = prompt
        existing.objective_id = focus_objective.id if focus_objective is not None else None
        existing.objective_slug = focus_objective.slug if focus_objective is not None else None
        existing.expected_answer = expected_answer
        existing.due_at = due_at
        existing.status = status
        existing.interval_days = interval_days
        existing.updated_at = now
        return existing

    def complete_review(self, review_item: ReviewItem, correctness: float) -> ReviewItem:
        now = utc_now()
        next_interval = (
            max(review_item.interval_days + 1, review_item.interval_days * 2)
            if correctness >= 0.8
            else max(2, review_item.interval_days + 1)
            if correctness >= 0.6
            else 1
        )
        review_item.review_count += 1
        review_item.last_reviewed_at = now
        review_item.interval_days = next_interval
        review_item.due_at = now + timedelta(days=next_interval)
        review_item.status = ReviewStatus.SCHEDULED if correctness >= 0.5 else ReviewStatus.DUE
        if correctness < 0.5:
            review_item.due_at = now
        review_item.updated_at = now
        return review_item
