from __future__ import annotations

from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import Settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LlmProvider:
    provider_name: str
    model_name: str

    def generate_text(
        self,
        prompt: str,
        instructions: str | None = None,
    ) -> str:
        raise NotImplementedError

    def generate_structured(
        self,
        prompt: str,
        schema: type[SchemaT],
        schema_name: str,
    ) -> SchemaT:
        raise NotImplementedError


class OpenAIResponsesProvider(LlmProvider):
    provider_name = "openai"

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI provider")
        self.settings = settings
        self.model_name = settings.openai_model
        self.http_client = http_client or httpx.Client(
            base_url=settings.openai_base_url.rstrip("/"),
            timeout=30.0,
        )

    def generate_text(
        self,
        prompt: str,
        instructions: str | None = None,
    ) -> str:
        response = self.http_client.post(
            "/responses",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.openai_model,
                "instructions": instructions,
                "input": prompt,
            },
        )
        response.raise_for_status()
        payload = response.json()
        output_text = payload.get("output_text")
        if output_text:
            return str(output_text).strip()

        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text = content.get("text")
                    if text:
                        return str(text).strip()

        raise ValueError("No text output returned by OpenAI Responses API")

    def generate_structured(
        self,
        prompt: str,
        schema: type[SchemaT],
        schema_name: str,
    ) -> SchemaT:
        response = self.http_client.post(
            "/responses",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.openai_model,
                "input": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "Return only a structured JSON evaluation."
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompt,
                            }
                        ],
                    },
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    }
                },
            },
        )
        response.raise_for_status()
        payload = response.json()

        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text = content.get("text")
                    if text:
                        return schema.model_validate_json(text)

        raise ValueError("No structured output returned by OpenAI Responses API")


class StubResponsesProvider(LlmProvider):
    provider_name = "stub"
    model_name = "stub-tutor-v1"

    def _extract_tag(self, prompt: str, tag: str) -> str:
        start_token = f"<{tag}>"
        end_token = f"</{tag}>"
        if start_token in prompt and end_token in prompt:
            return prompt.split(start_token, 1)[1].split(end_token, 1)[0].strip()
        return ""

    def _extract_field(self, prompt: str, field: str) -> str:
        for line in prompt.splitlines():
            if line.startswith(f"{field}:"):
                return line.split(":", 1)[1].strip()
        return ""

    def generate_text(
        self,
        prompt: str,
        instructions: str | None = None,
    ) -> str:
        del instructions
        action = self._extract_field(prompt, "requested_action")
        weak_objective = self._extract_field(prompt, "weak_objective")
        next_concept = self._extract_field(prompt, "next_concept")

        if action == "advance" and next_concept and next_concept != "none":
            next_title = next_concept.split(":", 1)[0].strip()
            return f"You are ready for {next_title}. Before we move, what connection do you see between this idea and {next_title}?"
        if action == "reinforce":
            return f"Let's tighten up {weak_objective.lower() or 'this part of the idea'}. Your answer is close, but one detail needs correcting before we continue."
        if action == "ask_diagnostic":
            return f"Let's focus on {weak_objective.lower() or 'the key idea'}. What does it mean in your own words, and why does it matter?"
        if action == "ask_practice":
            return f"Practice {weak_objective.lower() or 'this skill'} with one short example, then explain why your answer works."
        return f"Let's build intuition for {weak_objective.lower() or 'this concept'} and connect it to one concrete example."

    def generate_structured(
        self,
        prompt: str,
        schema: type[SchemaT],
        schema_name: str,
    ) -> SchemaT:
        if schema_name == "lesson_plan":
            objective_fields: list[tuple[str | None, str | None, str]] = []
            for line in prompt.splitlines():
                if line.strip().startswith("- id="):
                    parts = [part.strip() for part in line.replace("- ", "", 1).split("|")]
                    values: dict[str, str] = {}
                    for part in parts:
                        if "=" in part:
                            key, value = part.split("=", 1)
                            values[key.strip()] = value.strip()
                    objective_fields.append(
                        (
                            values.get("id"),
                            values.get("slug"),
                            values.get("title", "Objective"),
                        )
                    )
            steps = []
            for index, (objective_id, objective_slug, objective_title) in enumerate(objective_fields[:4] or [(None, None, "Core understanding")]):
                step_type = ["explain", "diagnostic", "practice", "review"][min(index, 3)]
                steps.append(
                    {
                        "title": f"{objective_title} step {index + 1}",
                        "objective_id": objective_id,
                        "objective_slug": objective_slug,
                        "instruction": f"Guide the learner through {objective_title.lower()} with one focused interaction.",
                        "rationale": f"This step strengthens {objective_title.lower()} before moving on.",
                        "step_type": step_type,
                    }
                )
            if len(steps) < 3:
                while len(steps) < 3:
                    steps.append(
                        {
                            "title": f"Practice step {len(steps) + 1}",
                            "objective_id": None,
                            "objective_slug": None,
                            "instruction": "Ask the learner to apply the topic in one short example.",
                            "rationale": "Application helps stabilize learning.",
                            "step_type": "practice",
                        }
                    )
            return schema.model_validate(
                {
                    "summary": "A short interactive lesson that builds understanding, checks reasoning, and reinforces the weakest areas.",
                    "steps": steps[:6],
                }
            )

        learner_message = self._extract_tag(prompt, "learner_message") or prompt
        lower_prompt = learner_message.lower()
        correctness = 0.35
        if "because" in lower_prompt or "for example" in lower_prompt or "means" in lower_prompt:
            correctness += 0.2
        if len(lower_prompt.split()) >= 12:
            correctness += 0.2
        if "maybe" in lower_prompt or "not sure" in lower_prompt or "i think" in lower_prompt:
            correctness -= 0.1
        confidence = 0.35 if ("maybe" in lower_prompt or "not sure" in lower_prompt or "i think" in lower_prompt) else 0.68
        misconception_detected = "always" in lower_prompt or "never" in lower_prompt or "same as" in lower_prompt
        misconception_description = (
            "Potential misunderstanding detected in the learner response."
            if misconception_detected
            else None
        )

        objective_id = None
        for line in prompt.splitlines():
            if line.strip().startswith("- id="):
                objective_id = line.split("|")[0].replace("- id=", "").strip()
                if any(keyword in lower_prompt for keyword in ("notation", "symbol", "vocabulary", "expression")) and "notation" in line.lower():
                    objective_id = line.split("|")[0].replace("- id=", "").strip()
                    break

        return schema.model_validate(
            {
                "correctness": min(1.0, max(0.0, correctness - (0.2 if misconception_detected else 0.0))),
                "confidence": confidence,
                "objective_id": objective_id,
                "misconception_detected": misconception_detected,
                "misconception_description": misconception_description,
                "reasoning": "Stub provider generated a deterministic structured evaluation for testing.",
            }
        )
