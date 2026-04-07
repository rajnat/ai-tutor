from app.models.domain import Learner, SessionMode, TutorAction


class TeachingService:
    def respond(
        self,
        learner: Learner,
        topic: str,
        action: TutorAction,
        learner_message: str,
        mode: SessionMode,
    ) -> str:
        style = learner.learning_style.teaching_style
        prefers_examples = learner.learning_style.prefers_examples

        if action == TutorAction.EXPLAIN:
            example = (
                f" Think of {topic} through a concrete example before we generalize."
                if prefers_examples
                else ""
            )
            return (
                f"Let's build intuition for {topic}. I'll keep this {style} and stepwise."
                f"{example} Tell me how you would explain the core idea back in your own words."
            )

        if action == TutorAction.ASK_DIAGNOSTIC:
            return (
                f"You’re making progress on {topic}. What is the key principle involved here,"
                " and why does it matter?"
            )

        if action == TutorAction.ASK_PRACTICE:
            return (
                f"Practice check for {topic}: answer this briefly and then justify it."
                f" Based on your current understanding, what is one correct application of {topic}?"
            )

        if action == TutorAction.REINFORCE:
            return (
                f"I want to tighten up one part of your understanding of {topic}."
                f" Your last answer suggested a possible gap: '{learner_message}'."
                " Let's correct that and then try one focused question."
            )

        if mode == SessionMode.ASK:
            return (
                f"Here’s the concise answer on {topic}, tailored to what you asked."
                " After you read it, tell me whether you want a deeper explanation or a quick check."
            )

        return (
            f"You’re showing solid understanding of {topic}. We can either go deeper,"
            " connect it to a harder example, or move to the next concept."
        )
