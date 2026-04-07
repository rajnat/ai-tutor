import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["ADAPTIVE_TUTOR_DATABASE_URL"] = (
    f"sqlite:///{Path(__file__).resolve().parent / 'test_adaptive_tutor.db'}"
)

from app.main import app


def test_healthcheck() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_create_learner_start_session_and_submit_turn() -> None:
    with TestClient(app) as client:
        learner_response = client.post(
            "/api/v1/learners",
            json={
                "name": "Eswar",
                "goal": "Learn calculus deeply",
                "initial_topic": "derivatives",
                "preferences": {
                    "verbosity": "medium",
                    "prefers_examples": True,
                    "teaching_style": "socratic",
                },
            },
        )
        assert learner_response.status_code == 200
        learner_id = learner_response.json()["id"]

        session_response = client.post(
            "/api/v1/sessions",
            json={"learner_id": learner_id, "topic": "derivatives", "mode": "learn"},
        )
        assert session_response.status_code == 200
        session_id = session_response.json()["id"]

        turn_response = client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "I think a derivative means how a function changes step by step."},
        )
        assert turn_response.status_code == 200
        payload = turn_response.json()
        assert payload["session_id"] == session_id
        assert payload["updated_session"]["turns"]
        assert payload["updated_learner"]["skills"]["derivatives"]["mastery"] >= 0.0
