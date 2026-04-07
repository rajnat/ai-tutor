import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

TEST_DB_PATH = Path(__file__).resolve().parent / "test_adaptive_tutor.db"

os.environ["ADAPTIVE_TUTOR_DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["ADAPTIVE_TUTOR_LLM_PROVIDER"] = "stub"

from app.main import app
from app.services.database import engine


def migrate_test_db() -> None:
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


def signup_and_auth_headers(
    client: TestClient,
    *,
    email: str = "eswar@example.com",
    password: str = "supersecure123",
    name: str = "Eswar",
    goal: str = "Learn calculus deeply",
    initial_topic: str | None = "derivatives",
) -> tuple[dict[str, str], dict]:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": password,
            "name": name,
            "goal": goal,
            "initial_topic": initial_topic,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    return {"Authorization": f"Bearer {payload['token']}"}, payload


def test_healthcheck() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_create_learner_start_session_and_submit_turn() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        headers, auth_payload = signup_and_auth_headers(client)
        learner_id = auth_payload["learner"]["id"]

        session_response = client.post(
            "/api/v1/sessions",
            json={"learner_id": learner_id, "topic": "derivatives", "mode": "learn"},
            headers=headers,
        )
        assert session_response.status_code == 200
        session_id = session_response.json()["id"]

        turn_response = client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "I think a derivative means how a function changes step by step."},
            headers=headers,
        )
        assert turn_response.status_code == 200
        payload = turn_response.json()
        assert payload["session_id"] == session_id
        assert payload["updated_session"]["turns"]
        assert payload["updated_learner"]["skills"]["derivatives"]["mastery"] >= 0.0


def test_due_reviews_and_review_completion() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        headers, auth_payload = signup_and_auth_headers(client, initial_topic=None)
        learner_id = auth_payload["learner"]["id"]

        session_response = client.post(
            "/api/v1/sessions",
            json={"learner_id": learner_id, "topic": "derivatives", "mode": "learn"},
            headers=headers,
        )
        session_id = session_response.json()["id"]

        turn_response = client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "maybe"},
            headers=headers,
        )
        assert turn_response.status_code == 200

        due_reviews = client.get(f"/api/v1/learners/{learner_id}/reviews/due", headers=headers)
        assert due_reviews.status_code == 200
        reviews = due_reviews.json()
        assert len(reviews) == 1
        assert reviews[0]["topic"] == "derivatives"

        completed = client.post(
            f"/api/v1/reviews/{reviews[0]['id']}/complete",
            json={"correct": True},
            headers=headers,
        )
        assert completed.status_code == 200
        assert completed.json()["review_count"] == 1
        assert completed.json()["status"] == "scheduled"


def test_curriculum_recommendations_respect_prerequisites() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        headers, auth_payload = signup_and_auth_headers(client, initial_topic="algebra")
        learner_id = auth_payload["learner"]["id"]

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
            headers=headers,
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
        headers, auth_payload = signup_and_auth_headers(client, initial_topic="algebra")
        learner_id = auth_payload["learner"]["id"]

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
            headers=headers,
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
                headers=headers,
            )
            assert turn_response.status_code == 200

        payload = turn_response.json()
        assert payload["tutor_action"] == "advance"
        assert payload["updated_session"]["topic"] == "derivatives"
        assert "Derivatives" in payload["tutor_response"]


def test_objective_threshold_blocks_premature_advancement() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        headers, auth_payload = signup_and_auth_headers(client, initial_topic="algebra")
        learner_id = auth_payload["learner"]["id"]

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
            headers=headers,
        )
        session_id = session_response.json()["id"]

        for _ in range(3):
            turn_response = client.post(
                f"/api/v1/sessions/{session_id}/turns",
                json={"message": "Because algebra means balancing equations step by step."},
                headers=headers,
            )
            assert turn_response.status_code == 200

        payload = turn_response.json()
        assert payload["tutor_action"] != "advance"
        assert payload["updated_session"]["topic"] == "algebra"


def test_tutor_response_targets_weak_objective() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        headers, auth_payload = signup_and_auth_headers(client, initial_topic="algebra")
        learner_id = auth_payload["learner"]["id"]

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
            headers=headers,
        )
        session_id = session_response.json()["id"]

        turn_response = client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "maybe algebra is like moving symbols around"},
            headers=headers,
        )
        assert turn_response.status_code == 200
        payload = turn_response.json()
        response_text = payload["tutor_response"].lower()
        assert "conceptual intuition" in response_text or "notation and vocabulary" in response_text
        assert payload["evaluation"]["objective_id"] is not None


def test_evaluation_updates_targeted_objective_only() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        headers, auth_payload = signup_and_auth_headers(
            client,
            goal="Learn algebra",
            initial_topic="algebra",
        )
        learner_id = auth_payload["learner"]["id"]

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
            headers=headers,
        )
        session_id = session_response.json()["id"]

        turn_response = client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "The notation uses symbols and vocabulary to describe expressions."},
            headers=headers,
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
        headers, auth_payload = signup_and_auth_headers(
            client,
            goal="Learn algebra",
            initial_topic="algebra",
        )
        learner_id = auth_payload["learner"]["id"]

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
            headers=headers,
        )
        session_id = session_response.json()["id"]
        client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "The notation uses symbols and vocabulary to describe expressions."},
            headers=headers,
        )

        progress_response = client.get(
            f"/api/v1/learners/{learner_id}/progress/objectives",
            params={"subject": "math"},
            headers=headers,
        )
        assert progress_response.status_code == 200
        payload = progress_response.json()
        assert len(payload) == 1
        assert payload[0]["concept"]["slug"] == "algebra"
        assert len(payload[0]["objectives"]) == 2


def test_material_suggestions_include_literature_friendly_supplements() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        headers, auth_payload = signup_and_auth_headers(
            client,
            goal="Learn Russian literature",
            initial_topic="russian-literature",
        )
        learner_id = auth_payload["learner"]["id"]

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
            headers=headers,
        )
        assert suggestions_response.status_code == 200
        payload = suggestions_response.json()
        assert len(payload) >= 3
        assert any(item["material_type"] == "comparison" for item in payload)


def test_lesson_plan_endpoint_returns_generated_plan() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        headers, auth_payload = signup_and_auth_headers(
            client,
            goal="Learn algebra",
            initial_topic="algebra",
        )
        learner_id = auth_payload["learner"]["id"]

        concept_response = client.post(
            "/api/v1/curriculum/concepts",
            json={
                "slug": "algebra",
                "title": "Algebra Foundations",
                "description": "Core algebraic manipulation.",
                "subject": "math",
                "prerequisites": [],
            },
        )
        assert concept_response.status_code == 200

        response = client.get(
            f"/api/v1/learners/{learner_id}/lesson-plan",
            params={"topic": "algebra"},
            headers=headers,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["topic"] == "algebra"
        assert len(payload["steps"]) >= 3
        assert payload["current_step_index"] >= 0
        assert isinstance(payload["completed_step_ids"], list)


def test_auth_login_me_and_logout_flow() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        signup_response = client.post(
            "/api/v1/auth/signup",
            json={
                "email": "auth@example.com",
                "password": "supersecure123",
                "name": "Eswar",
                "goal": "Learn algebra",
                "initial_topic": "algebra",
            },
        )
        assert signup_response.status_code == 200
        signup_payload = signup_response.json()
        token = signup_payload["token"]

        me_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["account"]["email"] == "auth@example.com"

        logout_response = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert logout_response.status_code == 200

        expired_me_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert expired_me_response.status_code == 401

        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "auth@example.com", "password": "supersecure123"},
        )
        assert login_response.status_code == 200
        assert login_response.json()["account"]["email"] == "auth@example.com"


def test_protected_routes_reject_cross_learner_access() -> None:
    migrate_test_db()
    with TestClient(app) as client:
        first_headers, first_auth_payload = signup_and_auth_headers(
            client,
            email="first@example.com",
            initial_topic="algebra",
        )
        _, second_auth_payload = signup_and_auth_headers(
            client,
            email="second@example.com",
            initial_topic="derivatives",
        )

        forbidden_response = client.get(
            f"/api/v1/learners/{second_auth_payload['learner']['id']}",
            headers=first_headers,
        )
        assert forbidden_response.status_code == 403

        forbidden_session = client.post(
            "/api/v1/sessions",
            json={
                "learner_id": second_auth_payload["learner"]["id"],
                "topic": "derivatives",
                "mode": "learn",
            },
            headers=first_headers,
        )
        assert forbidden_session.status_code == 403
