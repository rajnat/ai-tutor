from app.models.domain import EvaluationResult


class EvaluationService:
    _POSITIVE_SIGNALS = ("because", "therefore", "for example", "step", "means")
    _UNCERTAIN_SIGNALS = ("maybe", "i think", "not sure", "guess", "?")
    _MISCONCEPTION_SIGNALS = ("always", "never", "same as", "equal to")

    def evaluate(self, learner_message: str, topic: str) -> EvaluationResult:
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

        reasoning = (
            "Estimated understanding from answer length, explanatory detail, and confidence cues."
        )

        return EvaluationResult(
            correctness=correctness,
            confidence=confidence,
            misconception_detected=misconception_detected,
            misconception_description=misconception_description,
            reasoning=reasoning,
        )
