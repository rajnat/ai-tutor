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


def test_due_reviews_and_review_completion() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        learner_response = client.post(
            "/api/v1/learners",
            json={"name": "Eswar", "goal": "Learn calculus deeply"},
        )
        learner_id = learner_response.json()["id"]

        session_response = client.post(
            "/api/v1/sessions",
            json={"learner_id": learner_id, "topic": "derivatives", "mode": "learn"},
        )
        session_id = session_response.json()["id"]

        turn_response = client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "maybe"},
        )
        assert turn_response.status_code == 200

        due_reviews = client.get(f"/api/v1/learners/{learner_id}/reviews/due")
        assert due_reviews.status_code == 200
        reviews = due_reviews.json()
        assert len(reviews) == 1
        assert reviews[0]["topic"] == "derivatives"

        completed = client.post(f"/api/v1/reviews/{reviews[0]['id']}/complete", json={"correct": True})
        assert completed.status_code == 200
        assert completed.json()["review_count"] == 1
        assert completed.json()["status"] == "scheduled"


def test_curriculum_recommendations_respect_prerequisites() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        learner_response = client.post(
            "/api/v1/learners",
            json={
                "name": "Eswar",
                "goal": "Learn calculus deeply",
                "initial_topic": "algebra",
            },
        )
        learner_id = learner_response.json()["id"]

        concept_payloads = [
            {
                "slug": "algebra",
                "title": "Algebra Foundations",
                "description": "Core algebraic manipulation.",
                "subject": "math",
                "prerequisites": [],
            },
            {
                "slug": "derivatives",
                "title": "Derivatives",
                "description": "Rates of change.",
                "subject": "math",
                "prerequisites": ["algebra"],
            },
            {
                "slug": "integrals",
                "title": "Integrals",
                "description": "Accumulation and area.",
                "subject": "math",
                "prerequisites": ["derivatives"],
            },
        ]

        for payload in concept_payloads:
            response = client.post("/api/v1/curriculum/concepts", json=payload)
            assert response.status_code == 200

        recommendations = client.get(
            f"/api/v1/learners/{learner_id}/curriculum/recommendations",
            params={"subject": "math"},
        )
        assert recommendations.status_code == 200
        recommendation_payload = recommendations.json()
        slugs = [item["slug"] for item in recommendation_payload]
        assert "algebra" in slugs
        assert "derivatives" not in slugs
        assert len(recommendation_payload[0]["objectives"]) == 4


def test_session_advances_using_curriculum_graph() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        learner_response = client.post(
            "/api/v1/learners",
            json={
                "name": "Eswar",
                "goal": "Learn calculus deeply",
                "initial_topic": "algebra",
            },
        )
        learner_id = learner_response.json()["id"]

        concept_payloads = [
            {
                "slug": "algebra",
                "title": "Algebra Foundations",
                "description": "Core algebraic manipulation.",
                "subject": "math",
                "prerequisites": [],
            },
            {
                "slug": "derivatives",
                "title": "Derivatives",
                "description": "Rates of change.",
                "subject": "math",
                "prerequisites": ["algebra"],
            },
        ]
        for payload in concept_payloads:
            response = client.post("/api/v1/curriculum/concepts", json=payload)
            assert response.status_code == 200

        session_response = client.post(
            "/api/v1/sessions",
            json={"learner_id": learner_id, "topic": "algebra", "mode": "learn"},
        )
        session_id = session_response.json()["id"]

        strong_answer = (
            "Algebra lets us transform expressions because equivalent operations preserve"
            " relationships, and for example we isolate variables step by step to solve equations."
        )
        for _ in range(10):
            turn_response = client.post(
                f"/api/v1/sessions/{session_id}/turns",
                json={"message": strong_answer},
            )
            assert turn_response.status_code == 200

        payload = turn_response.json()
        assert payload["tutor_action"] == "advance"
        assert payload["updated_session"]["topic"] == "derivatives"
        assert "Derivatives" in payload["tutor_response"]


def test_objective_threshold_blocks_premature_advancement() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        learner_response = client.post(
            "/api/v1/learners",
            json={"name": "Eswar", "goal": "Learn calculus deeply", "initial_topic": "algebra"},
        )
        learner_id = learner_response.json()["id"]

        for payload in [
            {
                "slug": "algebra",
                "title": "Algebra Foundations",
                "description": "Core algebraic manipulation.",
                "subject": "math",
                "prerequisites": [],
            },
            {
                "slug": "derivatives",
                "title": "Derivatives",
                "description": "Rates of change.",
                "subject": "math",
                "prerequisites": ["algebra"],
            },
        ]:
            response = client.post("/api/v1/curriculum/concepts", json=payload)
            assert response.status_code == 200

        session_response = client.post(
            "/api/v1/sessions",
            json={"learner_id": learner_id, "topic": "algebra", "mode": "learn"},
        )
        session_id = session_response.json()["id"]

        for _ in range(3):
            turn_response = client.post(
                f"/api/v1/sessions/{session_id}/turns",
                json={"message": "Because algebra means balancing equations step by step."},
            )
            assert turn_response.status_code == 200

        payload = turn_response.json()
        assert payload["tutor_action"] != "advance"
        assert payload["updated_session"]["topic"] == "algebra"


def test_tutor_response_targets_weak_objective() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        learner_response = client.post(
            "/api/v1/learners",
            json={"name": "Eswar", "goal": "Learn calculus deeply", "initial_topic": "algebra"},
        )
        learner_id = learner_response.json()["id"]

        concept_response = client.post(
            "/api/v1/curriculum/concepts",
            json={
                "slug": "algebra",
                "title": "Algebra Foundations",
                "description": "Core algebraic manipulation.",
                "subject": "math",
                "prerequisites": [],
                "objectives": ["Conceptual intuition", "Notation and vocabulary"],
            },
        )
        assert concept_response.status_code == 200

        session_response = client.post(
            "/api/v1/sessions",
            json={"learner_id": learner_id, "topic": "algebra", "mode": "learn"},
        )
        session_id = session_response.json()["id"]

        turn_response = client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "maybe algebra is like moving symbols around"},
        )
        assert turn_response.status_code == 200
        payload = turn_response.json()
        response_text = payload["tutor_response"].lower()
        assert "conceptual intuition" in response_text or "notation and vocabulary" in response_text
        assert payload["evaluation"]["objective_id"] is not None


def test_evaluation_updates_targeted_objective_only() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        learner_response = client.post(
            "/api/v1/learners",
            json={"name": "Eswar", "goal": "Learn algebra", "initial_topic": "algebra"},
        )
        learner_id = learner_response.json()["id"]

        concept_response = client.post(
            "/api/v1/curriculum/concepts",
            json={
                "slug": "algebra",
                "title": "Algebra Foundations",
                "description": "Core algebraic manipulation.",
                "subject": "math",
                "prerequisites": [],
                "objectives": ["Conceptual intuition", "Notation and vocabulary"],
            },
        )
        concept = concept_response.json()
        intuition_objective = next(obj for obj in concept["objectives"] if "intuition" in obj["slug"])
        notation_objective = next(obj for obj in concept["objectives"] if "notation" in obj["slug"])

        session_response = client.post(
            "/api/v1/sessions",
            json={"learner_id": learner_id, "topic": "algebra", "mode": "learn"},
        )
        session_id = session_response.json()["id"]

        turn_response = client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "The notation uses symbols and vocabulary to describe expressions."},
        )
        assert turn_response.status_code == 200
        payload = turn_response.json()
        assert payload["evaluation"]["objective_id"] == notation_objective["id"]
        objective_states = payload["updated_learner"]["objective_states"]
        assert objective_states[notation_objective["id"]]["mastery"] > 0.0
        assert objective_states[intuition_objective["id"]]["mastery"] == 0.0


def test_objective_progress_endpoint_groups_progress_by_concept() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        learner_response = client.post(
            "/api/v1/learners",
            json={"name": "Eswar", "goal": "Learn algebra", "initial_topic": "algebra"},
        )
        learner_id = learner_response.json()["id"]

        concept_response = client.post(
            "/api/v1/curriculum/concepts",
            json={
                "slug": "algebra",
                "title": "Algebra Foundations",
                "description": "Core algebraic manipulation.",
                "subject": "math",
                "prerequisites": [],
                "objectives": ["Conceptual intuition", "Notation and vocabulary"],
            },
        )
        assert concept_response.status_code == 200

        session_response = client.post(
            "/api/v1/sessions",
            json={"learner_id": learner_id, "topic": "algebra", "mode": "learn"},
        )
        session_id = session_response.json()["id"]
        client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "The notation uses symbols and vocabulary to describe expressions."},
        )

        progress_response = client.get(
            f"/api/v1/learners/{learner_id}/progress/objectives",
            params={"subject": "math"},
        )
        assert progress_response.status_code == 200
        payload = progress_response.json()
        assert len(payload) == 1
        assert payload[0]["concept"]["slug"] == "algebra"
        assert len(payload[0]["objectives"]) == 2


def test_material_suggestions_include_literature_friendly_supplements() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        learner_response = client.post(
            "/api/v1/learners",
            json={"name": "Eswar", "goal": "Learn Russian literature", "initial_topic": "russian-literature"},
        )
        learner_id = learner_response.json()["id"]

        concept_response = client.post(
            "/api/v1/curriculum/concepts",
            json={
                "slug": "russian-literature",
                "title": "Russian Literature",
                "description": "Major themes, authors, and historical context in Russian literature.",
                "subject": "literature",
                "prerequisites": [],
                "objectives": ["Historical context", "Theme comparison"],
            },
        )
        assert concept_response.status_code == 200

        suggestions_response = client.get(
            f"/api/v1/learners/{learner_id}/materials/suggestions",
            params={"topic": "russian-literature"},
        )
        assert suggestions_response.status_code == 200
        payload = suggestions_response.json()
        assert len(payload) >= 3
        assert any(item["material_type"] == "comparison" for item in payload)
