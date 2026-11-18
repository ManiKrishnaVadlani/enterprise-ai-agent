import builtins
import hashlib

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.embeddings import LocalEmbeddingProvider
from app.llm import ExtractiveAnswerProvider
from app.rag import NO_DOCUMENTS_ANSWER
from app.services import build_services
from main import create_app


pytestmark = pytest.mark.http


def test_local_mode_runs_upload_retrieval_citations_and_delete_without_openai(
    monkeypatch, tmp_path
):
    original_import = builtins.__import__

    def reject_openai_import(name, *args, **kwargs):
        if name == "openai":
            raise AssertionError("Local demo mode must not import or call OpenAI.")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_openai_import)
    settings = Settings(
        ai_mode="local",
        llm_provider="extractive",
        openai_api_key=None,
        database_path=tmp_path / "local-demo.db",
        chunk_size=500,
        chunk_overlap=50,
        min_relevance_score=0.1,
    )
    services = build_services(settings)
    user = services.store.create_user("Local mode test user")
    token = "eak_local_test_" + ("x" * 32)
    services.store.store_api_token_hash(
        user.user_id, hashlib.sha256(token.encode("utf-8")).hexdigest()
    )
    application = create_app(settings=settings, services=services)
    client = TestClient(application)
    client.headers.update({"Authorization": f"Bearer {token}"})

    upload = client.post(
        "/documents/upload",
        headers={"X-Filename": "policy.txt", "Content-Type": "application/octet-stream"},
        content=(
            b"Remote access requires multifactor authentication. "
            b"The company reviews access quarterly."
        ),
    )

    assert upload.status_code == 201
    document_id = upload.json()["document_id"]
    services = application.state.services
    assert isinstance(services.documents.embeddings, LocalEmbeddingProvider)
    assert isinstance(services.rag.language_model, ExtractiveAnswerProvider)

    listed = client.get("/documents")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    response = client.post(
        "/ask", json={"question": "What authentication is required for remote connections?"}
    )
    assert response.status_code == 200
    assert response.json()["answer"] == (
        "Remote access requires multifactor authentication. "
        "[Source 1: policy.txt]"
    )
    assert response.json()["sources"][0]["document_id"] == document_id
    assert response.json()["sources"][0]["filename"] == "policy.txt"

    no_match = client.post("/ask", json={"question": "When does the cafeteria close?"})
    assert no_match.status_code == 200
    assert no_match.json()["answer"] == NO_DOCUMENTS_ANSWER
    assert no_match.json()["sources"] == []

    deleted = client.delete(f"/documents/{document_id}")
    assert deleted.status_code == 204
    assert client.get("/documents").json() == {"documents": [], "total": 0}
    assert client.post("/ask", json={"question": "Remote access?"}).json()["answer"] == (
        NO_DOCUMENTS_ANSWER
    )
