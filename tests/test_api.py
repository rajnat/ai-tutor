import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

TEST_DB_PATH = Path(__file__).resolve().parent / "test_adaptive_tutor.db"

os.environ["ADAPTIVE_TUTOR_DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from app.main import app
from app.services.database import engine


def migrate_test_db() -> None:
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


def test_healthcheck() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_create_learner_start_session_and_submit_turn() -> None:
    migrate_test_db()
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
