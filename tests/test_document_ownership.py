import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.embeddings import LocalEmbeddingProvider
from app.models import DocumentChunk
from app.rag import NO_DOCUMENTS_ANSWER
from app.services import build_services
from main import create_app


pytestmark = pytest.mark.http


def _application(tmp_path):
    settings = Settings(
        ai_mode="local",
        database_path=tmp_path / "ownership.db",
        min_relevance_score=0.15,
    )
    services = build_services(settings)
    app = create_app(settings=settings, services=services)
    return app, services


def _client(app, store, user_id: str) -> TestClient:
    token = f"eak_test_{user_id}_" + ("s" * 32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    store.store_api_token_hash(user_id, token_hash, label=f"test {user_id}")
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def test_document_endpoints_require_authentication_but_health_is_public(tmp_path):
    app, _services = _application(tmp_path)
    client = TestClient(app)
    document_id = str(uuid4())
    upload_headers = {
        "X-Filename": "policy.txt",
        "Content-Type": "application/octet-stream",
    }

    responses = [
        client.post("/documents/upload", headers=upload_headers, content=b"A policy."),
        client.get("/documents"),
        client.delete(f"/documents/{document_id}"),
        client.post("/ask", json={"question": "What is the policy?"}),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 401]
    assert client.get("/health").status_code == 200


def test_users_can_only_list_retrieve_and_delete_their_own_documents(tmp_path):
    app, services = _application(tmp_path)
    alice = services.store.create_user("Alice")
    bob = services.store.create_user("Bob")
    alice_client = _client(app, services.store, alice.user_id)
    bob_client = _client(app, services.store, bob.user_id)
    headers = {
        "X-Filename": "policy.txt",
        "Content-Type": "application/octet-stream",
    }

    alice_upload = alice_client.post(
        "/documents/upload",
        headers=headers,
        content=b"The blue visitor badge is cobalt.",
    )
    bob_upload = bob_client.post(
        "/documents/upload",
        headers=headers,
        content=b"The private vault marker is zebra.",
    )
    assert alice_upload.status_code == 201
    assert bob_upload.status_code == 201
    alice_document_id = alice_upload.json()["document_id"]
    bob_document_id = bob_upload.json()["document_id"]

    assert [item.document_id for item in services.store.list_documents(owner_id=alice.user_id)] == [
        alice_document_id
    ]
    assert [item.document_id for item in services.store.list_documents(owner_id=bob.user_id)] == [
        bob_document_id
    ]
    assert [item["document_id"] for item in alice_client.get("/documents").json()["documents"]] == [
        alice_document_id
    ]
    assert [item["document_id"] for item in bob_client.get("/documents").json()["documents"]] == [
        bob_document_id
    ]

    alice_answer = alice_client.post(
        "/ask", json={"question": "What marker identifies the private vault?"}
    )
    bob_answer = bob_client.post(
        "/ask", json={"question": "What marker identifies the private vault?"}
    )
    assert alice_answer.status_code == 200
    assert alice_answer.json()["answer"] == NO_DOCUMENTS_ANSWER
    assert alice_answer.json()["sources"] == []
    assert bob_answer.status_code == 200
    assert "zebra" in bob_answer.json()["answer"]
    assert bob_answer.json()["sources"][0]["document_id"] == bob_document_id

    cross_owner_question = alice_client.post(
        "/ask",
        json={
            "question": "What marker identifies the private vault?",
            "document_id": bob_document_id,
        },
    )
    denied_delete = alice_client.delete(f"/documents/{bob_document_id}")
    missing_delete = alice_client.delete(
        f"/documents/{uuid4()}"
    )
    assert cross_owner_question.status_code == 404
    assert denied_delete.status_code == 404
    assert missing_delete.status_code == 404
    assert denied_delete.json() == missing_delete.json()
    assert [item["document_id"] for item in bob_client.get("/documents").json()["documents"]] == [
        bob_document_id
    ]

    assert bob_client.delete(f"/documents/{bob_document_id}").status_code == 204
    assert bob_client.get("/documents").json()["total"] == 0


def test_ownerless_legacy_documents_remain_stored_but_are_inaccessible(tmp_path):
    app, services = _application(tmp_path)
    user = services.store.create_user("Current user")
    client = _client(app, services.store, user.user_id)
    document_id = str(uuid4())
    text = "Legacy ownerless policy says the marker is amethyst."
    chunk = DocumentChunk(
        chunk_id=str(uuid4()),
        document_id=document_id,
        filename="legacy.txt",
        text=text,
        page_number=None,
        ingested_at=datetime.now(timezone.utc),
    )
    vector = LocalEmbeddingProvider().embed([text])
    services.store.add_document(document_id, "legacy.txt", [chunk], vector)

    assert client.get("/documents").json() == {"documents": [], "total": 0}
    assert client.post(
        "/ask", json={"question": "What marker is in the legacy policy?"}
    ).json()["sources"] == []
    assert client.post(
        "/ask",
        json={
            "question": "What marker is in the legacy policy?",
            "document_id": document_id,
        },
    ).status_code == 404
    assert client.delete(f"/documents/{document_id}").status_code == 404
    assert [document.document_id for document in services.store.list_documents()] == [
        document_id
    ]


def test_api_rejects_malformed_document_ids_as_validation_errors(tmp_path):
    app, services = _application(tmp_path)
    user = services.store.create_user("UUID test user")
    client = _client(app, services.store, user.user_id)

    assert client.delete("/documents/not-a-uuid").status_code == 422
    assert client.post(
        "/ask", json={"question": "Question?", "document_id": "not-a-uuid"}
    ).status_code == 422
