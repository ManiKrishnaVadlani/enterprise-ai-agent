"""Deterministic smoke evaluation for extraction, chunking, and RAG compatibility."""

import pytest

from app.document_service import DocumentService
from app.embeddings import LocalEmbeddingProvider
from app.errors import DocumentNotFoundError
from app.llm import ExtractiveAnswerProvider, NO_INFORMATION_ANSWER
from app.rag import RAGPipeline
from app.vector_store import SQLiteVectorStore


def test_processed_document_supports_grounded_answers_abstention_and_isolation(tmp_path):
    store = SQLiteVectorStore(tmp_path / "processing-evaluation.db")
    alice = store.create_user("Alice")
    bob = store.create_user("Bob")
    embeddings = LocalEmbeddingProvider()
    documents = DocumentService(
        store,
        embeddings,
        chunk_size=100,
        chunk_overlap=20,
        max_upload_bytes=10_000,
    )
    policy = documents.ingest(
        "access-policy.txt",
        (
            "Access Policy\r\n\r\n"
            "Account access reviews happen quarterly. Security owners record each result.\r\n\r\n"
            "Remote access requires multifactor authentication."
        ).encode("utf-8"),
        owner_id=alice.user_id,
    )
    secret = documents.ingest(
        "private.txt",
        b"The recovery phrase is amber canyon.",
        owner_id=bob.user_id,
    )
    pipeline = RAGPipeline(
        store,
        embeddings,
        ExtractiveAnswerProvider(),
        top_k=3,
        min_relevance_score=0.0,
    )

    supported = pipeline.answer(
        "When do access reviews happen?", owner_id=alice.user_id
    )
    assert "quarterly" in supported.answer.lower()
    assert [source.document_id for source in supported.sources] == [policy.document_id]
    assert all(source.filename == "access-policy.txt" for source in supported.sources)

    unsupported = pipeline.answer(
        "What is the office fax number?", owner_id=alice.user_id
    )
    assert unsupported.answer == NO_INFORMATION_ANSWER
    assert unsupported.sources == []

    private_question = pipeline.answer(
        "What is the recovery phrase?", owner_id=alice.user_id
    )
    assert private_question.answer == NO_INFORMATION_ANSWER
    assert all(source.document_id != secret.document_id for source in private_question.sources)

    with pytest.raises(DocumentNotFoundError):
        pipeline.answer(
            "What is the recovery phrase?",
            document_id=secret.document_id,
            owner_id=alice.user_id,
        )

    documents.delete_document(policy.document_id, owner_id=alice.user_id)
    assert documents.list_documents(owner_id=alice.user_id) == []
    assert documents.list_documents(owner_id=bob.user_id)[0].document_id == secret.document_id
