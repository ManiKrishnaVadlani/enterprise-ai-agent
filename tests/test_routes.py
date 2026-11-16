import pytest
from fastapi.testclient import TestClient

from app.config import APP_NAME, Settings
from main import create_app


pytestmark = pytest.mark.http


@pytest.fixture
def client(tmp_path):
    return TestClient(
        create_app(settings=Settings(database_path=tmp_path / "routes.db"))
    )


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
