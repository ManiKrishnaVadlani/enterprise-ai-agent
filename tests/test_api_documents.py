import hashlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.document_service import DocumentService
from app.embeddings import OpenAIEmbeddingProvider
from app.llm import OpenAILanguageModel
from app.models import DocumentChunk
from app.rag import RAGPipeline
from app.services import ApplicationServices
from app.vector_store import SQLiteVectorStore
from main import create_app


pytestmark = pytest.mark.http


class FakeEmbeddings:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeLanguageModel:
    def generate_answer(self, question, context):
        assert question == "How should remote access be secured?"
        assert "[Source 1: policy.txt]" in context
        return "Use multifactor authentication. [Source 1]"


def _client(tmp_path, max_upload_bytes=1000):
    settings = Settings(
        database_path=tmp_path / "api.db",
        chunk_size=100,
        chunk_overlap=10,
        max_upload_bytes=max_upload_bytes,
    )
    store = SQLiteVectorStore(settings.database_path)
    embeddings = FakeEmbeddings()
    services = ApplicationServices(
        store=store,
        documents=DocumentService(
            store, embeddings, settings.chunk_size, settings.chunk_overlap,
            settings.max_upload_bytes,
        ),
        rag=RAGPipeline(store, embeddings, FakeLanguageModel()),
    )
    user = store.create_user("API test user")
    token = "eak_api_test_token_" + ("x" * 32)
    store.store_api_token_hash(
        user.user_id, hashlib.sha256(token.encode("utf-8")).hexdigest()
    )
    client = TestClient(create_app(settings=settings, services=services))
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_upload_list_ask_with_citations_and_delete_document(tmp_path):
    client = _client(tmp_path)
    upload = client.post(
        "/documents/upload",
        headers={"X-Filename": "policy.txt", "Content-Type": "application/octet-stream"},
        content=b"Remote access requires multifactor authentication.",
    )

    assert upload.status_code == 201
    document_id = upload.json()["document_id"]
    assert upload.json()["filename"] == "policy.txt"
    assert upload.json()["chunk_count"] == 1

    listed = client.get("/documents")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["documents"][0]["document_id"] == document_id

    answer = client.post(
        "/ask", json={"question": "How should remote access be secured?"}
    )
    assert answer.status_code == 200
    assert answer.json()["answer"] == "Use multifactor authentication. [Source 1]"
    assert answer.json()["sources"][0]["document_id"] == document_id
    assert answer.json()["sources"][0]["filename"] == "policy.txt"

    deleted = client.delete(f"/documents/{document_id}")
    assert deleted.status_code == 204
    assert client.get("/documents").json() == {"documents": [], "total": 0}


def test_upload_rejects_invalid_filename_content_and_oversize(tmp_path):
    client = _client(tmp_path, max_upload_bytes=10)

    invalid_name = client.post(
        "/documents/upload", headers={"X-Filename": "../policy.txt"}, content=b"x"
    )
    assert invalid_name.status_code == 400

    unsupported = client.post(
        "/documents/upload", headers={"X-Filename": "policy.csv"}, content=b"x"
    )
    assert unsupported.status_code == 400

    oversized = client.post(
        "/documents/upload", headers={"X-Filename": "policy.txt"}, content=b"x" * 11
    )
    assert oversized.status_code == 400


def test_upload_rejects_declared_oversize_before_reading_body(tmp_path):
    client = _client(tmp_path, max_upload_bytes=10)
    response = client.post(
        "/documents/upload",
        headers={
            "X-Filename": "policy.txt",
            "Content-Length": "11",
            "Content-Type": "application/octet-stream",
        },
        content=b"x",
    )
    assert response.status_code == 400
    assert "upload limit" in response.json()["detail"]


def test_authenticated_rate_limit_and_cors_filename_header(tmp_path):
    from app.limits import UserRateLimiter

    client = _client(tmp_path)
    client.app.state.rate_limiter = UserRateLimiter(1, 60)
    first = client.get("/documents")
    limited = client.get("/documents")
    assert first.status_code == 200
    assert limited.status_code == 429
    assert limited.headers["retry-after"]
    assert client.get("/health").status_code == 200

    preflight = client.options(
        "/documents/upload",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,x-filename",
        },
    )
    assert preflight.status_code == 200
    assert "x-filename" in preflight.headers["access-control-allow-headers"].lower()


def test_delete_unknown_document_returns_not_found(tmp_path):
    response = _client(tmp_path).delete(
        "/documents/00000000-0000-0000-0000-000000000001"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "The requested document was not found."}


def test_provider_configuration_error_is_safe_and_uses_service_unavailable(tmp_path):
    settings = Settings(database_path=tmp_path / "provider-error.db")
    store = SQLiteVectorStore(settings.database_path)
    user = store.create_user("API provider test user")
    now = datetime.now(timezone.utc)
    chunk = DocumentChunk(
        chunk_id="stored-chunk",
        document_id="stored-document",
        filename="policy.txt",
        text="A policy passage.",
        page_number=None,
        ingested_at=now,
    )
    store.add_document(
        "stored-document", "policy.txt", [chunk], [[1.0, 0.0]],
        owner_id=user.user_id,
    )
    embeddings = OpenAIEmbeddingProvider(None, "model")
    services = ApplicationServices(
        store=store,
        documents=DocumentService(
            store, FakeEmbeddings(), settings.chunk_size, settings.chunk_overlap,
            settings.max_upload_bytes,
        ),
        rag=RAGPipeline(
            store, embeddings, OpenAILanguageModel(None, "model")
        ),
    )

    token = "eak_api_provider_test_" + ("x" * 32)
    store.store_api_token_hash(
        user.user_id, hashlib.sha256(token.encode("utf-8")).hexdigest()
    )
    client = TestClient(create_app(settings, services))
    response = client.post(
        "/ask",
        json={"question": "What does the policy say?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Set OPENAI_API_KEY before uploading documents or asking questions."
    }
