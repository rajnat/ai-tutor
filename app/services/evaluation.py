from app.models.domain import ConceptObjective, EvaluationResult


class EvaluationService:
    _POSITIVE_SIGNALS = ("because", "therefore", "for example", "step", "means")
    _UNCERTAIN_SIGNALS = ("maybe", "i think", "not sure", "guess", "?")
    _MISCONCEPTION_SIGNALS = ("always", "never", "same as", "equal to")
    _OBJECTIVE_HINTS = {
        "intuition": ("why", "meaning", "intuition", "idea", "concept"),
        "notation": ("notation", "symbol", "term", "vocabulary", "expression"),
        "application": ("apply", "solve", "compute", "calculate", "step"),
        "transfer": ("example", "compare", "connect", "real-world", "explain"),
    }

    def evaluate(
        self,
        learner_message: str,
        topic: str,
        objectives: list[ConceptObjective] | None = None,
    ) -> EvaluationResult:
        text = learner_message.strip().lower()
        word_count = len(text.split())

        correctness = 0.35
        if word_count >= 12:
            correctness += 0.2
        if any(signal in text for signal in self._POSITIVE_SIGNALS):
            correctness += 0.2

        confidence = 0.65
        if any(signal in text for signal in self._UNCERTAIN_SIGNALS):
            confidence = 0.35

        misconception_detected = any(signal in text for signal in self._MISCONCEPTION_SIGNALS)
        misconception_description = None
        if misconception_detected:
            misconception_description = f"Potential oversimplification detected in {topic}"
            correctness -= 0.2

        correctness = min(1.0, max(0.0, correctness))
        objective_id = self._classify_objective(text=text, objectives=objectives or [])

        reasoning = (
            "Estimated understanding from answer length, explanatory detail, and confidence cues."
        )

        return EvaluationResult(
            correctness=correctness,
            confidence=confidence,
            objective_id=objective_id,
            misconception_detected=misconception_detected,
            misconception_description=misconception_description,
            reasoning=reasoning,
        )

    def _classify_objective(self, text: str, objectives: list[ConceptObjective]) -> str | None:
        if not objectives:
            return None

        best_score = -1
        best_objective: ConceptObjective | None = None
        for objective in objectives:
            objective_text = f"{objective.slug} {objective.title} {objective.description}".lower()
            score = 0
            for label, keywords in self._OBJECTIVE_HINTS.items():
                if label in objective_text:
                    score += sum(1 for keyword in keywords if keyword in text)
            score += sum(1 for token in objective.title.lower().split() if token in text)
            if score > best_score:
                best_score = score
                best_objective = objective

        return best_objective.id if best_score > 0 else objectives[0].id
