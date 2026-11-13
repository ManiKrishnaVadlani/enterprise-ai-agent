from fastapi.testclient import TestClient

from app.config import APP_NAME
from main import app


client = TestClient(app)


def test_root_returns_project_status():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": APP_NAME,
        "status": "running",
    }


def test_health_returns_healthy_status():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "application": APP_NAME,
    }


def test_ask_accepts_a_valid_question():
    response = client.post("/ask", json={"question": "What is machine learning?"})

    assert response.status_code == 200
    assert response.json() == {
        "question": "What is machine learning?",
        "answer": (
            "Your question has been received. AI answering functionality "
            "will be added in a later stage."
        ),
    }


def test_ask_rejects_an_empty_question():
    response = client.post("/ask", json={"question": ""})

    assert response.status_code == 422
