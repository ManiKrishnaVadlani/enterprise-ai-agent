"""Small, deterministic retrieval smoke set for the local demo providers."""

from datetime import datetime, timezone

import pytest

from app.embeddings import LocalEmbeddingProvider
from app.errors import DocumentNotFoundError
from app.llm import ExtractiveAnswerProvider, NO_INFORMATION_ANSWER
from app.models import DocumentChunk
from app.rag import NO_DOCUMENTS_ANSWER, RAGPipeline
from app.vector_store import SQLiteVectorStore


def test_local_retrieval_smoke_set_covers_topics_citations_and_no_information(tmp_path):
    store = SQLiteVectorStore(tmp_path / "evaluation.db")
    user = store.create_user("Evaluation user")
    documents = {
        "security.txt": (
            "Access reviews happen quarterly. Multifactor authentication is required "
            "for remote access."
        ),
        "expenses.txt": (
            "Travel expense claims require receipts within ten days."
        ),
    }
    embeddings = LocalEmbeddingProvider()
    for index, (filename, text) in enumerate(documents.items()):
        document_id = f"evaluation-{index}"
        chunk = DocumentChunk(
            chunk_id=f"chunk-{index}",
            document_id=document_id,
            filename=filename,
            text=text,
            page_number=None,
            ingested_at=datetime.now(timezone.utc),
        )
        store.add_document(
            document_id,
            filename,
            [chunk],
            embeddings.embed([text]),
            owner_id=user.user_id,
        )

    pipeline = RAGPipeline(
        store,
        embeddings,
        ExtractiveAnswerProvider(),
        top_k=2,
        min_relevance_score=0.15,
    )

    evaluation_cases = [
        ("When do access reviews happen?", "security.txt", "quarterly"),
        ("What must travel expense claims include?", "expenses.txt", "receipts"),
    ]
    for question, expected_filename, expected_answer_text in evaluation_cases:
        result = pipeline.answer(question, owner_id=user.user_id)
        assert expected_answer_text in result.answer.lower()
        assert result.sources
        assert result.sources[0].filename == expected_filename
        assert expected_filename in result.answer

    # Baseline observation: with these exact local feature hashes,
    # "cafeteria access reviewed" scores 0.3086 against security.txt and
    # therefore passes the 0.15 retrieval threshold. The answer selector
    # must still abstain because only one of three content terms overlaps.
    incidental = pipeline.answer(
        "When is cafeteria access reviewed?", owner_id=user.user_id
    )
    assert incidental.answer == NO_INFORMATION_ANSWER
    assert incidental.sources == []

    unsupported = pipeline.answer(
        "What is the office fax number?", owner_id=user.user_id
    )
    assert unsupported.answer == NO_DOCUMENTS_ANSWER
    assert unsupported.sources == []


def test_document_specific_and_user_scoped_evaluation(tmp_path):
    store = SQLiteVectorStore(tmp_path / "scoped-evaluation.db")
    alice = store.create_user("Alice")
    bob = store.create_user("Bob")
    embeddings = LocalEmbeddingProvider()
    records = [
        ("alice-policy", "alice.txt", "Access reviews happen quarterly.", alice.user_id),
        ("bob-secret", "bob.txt", "The vault code is violet.", bob.user_id),
    ]
    for document_id, filename, text, owner_id in records:
        chunk = DocumentChunk(
            f"chunk-{document_id}", document_id, filename, text, None,
            datetime.now(timezone.utc),
        )
        store.add_document(
            document_id, filename, [chunk], embeddings.embed([text]), owner_id=owner_id
        )
    pipeline = RAGPipeline(store, embeddings, ExtractiveAnswerProvider())

    scoped = pipeline.answer(
        "When do access reviews happen?",
        document_id="alice-policy",
        owner_id=alice.user_id,
    )
    assert "quarterly" in scoped.answer
    assert [source.document_id for source in scoped.sources] == ["alice-policy"]
    alice_answer = pipeline.answer("What is the vault code?", owner_id=alice.user_id)
    assert alice_answer.answer == NO_DOCUMENTS_ANSWER
    assert alice_answer.sources == []
    with pytest.raises(DocumentNotFoundError):
        pipeline.answer(
            "What is the vault code?",
            document_id="bob-secret",
            owner_id=alice.user_id,
        )
