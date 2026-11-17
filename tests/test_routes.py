import hashlib

import pytest
from fastapi.testclient import TestClient

from app.config import APP_NAME, Settings
from app.services import build_services
from main import create_app


pytestmark = pytest.mark.http


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_path=tmp_path / "routes.db")
    services = build_services(settings)
    user = services.store.create_user("Route test user")
    token = "eak_route_test_" + ("x" * 32)
    services.store.store_api_token_hash(
        user.user_id, hashlib.sha256(token.encode("utf-8")).hexdigest()
    )
    test_client = TestClient(create_app(settings=settings, services=services))
    test_client.headers.update({"Authorization": f"Bearer {token}"})
    return test_client


def test_root_returns_project_status(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": APP_NAME,
        "status": "running",
    }


def test_health_returns_healthy_status(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "application": APP_NAME,
    }


def test_health_and_readiness_remain_public(client):
    anonymous = TestClient(client.app)

    assert anonymous.get("/health").status_code == 200
    assert anonymous.get("/ready").status_code == 200


def test_ask_accepts_a_valid_question(client):
    response = client.post("/ask", json={"question": "What is machine learning?"})

    assert response.status_code == 200
    assert response.json() == {
        "question": "What is machine learning?",
        "answer": "I could not find relevant information in the indexed documents.",
        "sources": [],
    }


def test_ask_rejects_an_empty_question(client):
    response = client.post("/ask", json={"question": ""})

    assert response.status_code == 422
