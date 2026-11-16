from datetime import datetime, timezone

import pytest

from app.errors import StorageError
from app.models import DocumentChunk
from app.vector_store import SQLiteVectorStore


def _chunk(document_id, chunk_id, filename, text):
    return DocumentChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        filename=filename,
        text=text,
        page_number=1,
        ingested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_store_persists_chunks_and_searches_by_cosine_similarity(tmp_path):
    database = tmp_path / "vectors.db"
    store = SQLiteVectorStore(database)
    store.add_document(
        "doc-a",
        "guide.txt",
        [_chunk("doc-a", "a1", "guide.txt", "security policy")],
        [[1.0, 0.0]],
    )

    reloaded_store = SQLiteVectorStore(database)
    results = reloaded_store.search([0.9, 0.1], top_k=3)

    assert len(results) == 1
    assert results[0].chunk.text == "security policy"
    assert results[0].chunk.page_number == 1
    assert results[0].score == pytest.approx(0.9939, abs=0.001)


def test_store_filters_search_by_document_id(tmp_path):
    store = SQLiteVectorStore(tmp_path / "vectors.db")
    store.add_document(
        "doc-a", "a.txt", [_chunk("doc-a", "a1", "a.txt", "alpha")], [[1.0, 0.0]]
    )
    store.add_document(
        "doc-b", "b.txt", [_chunk("doc-b", "b1", "b.txt", "beta")], [[0.0, 1.0]]
    )

    results = store.search([0.0, 1.0], top_k=5, document_id="doc-a")

    assert [result.chunk.document_id for result in results] == ["doc-a"]


def test_store_lists_chunk_counts_and_deletes_document_chunks(tmp_path):
    store = SQLiteVectorStore(tmp_path / "vectors.db")
    store.add_document(
        "doc-a",
        "guide.txt",
        [
            _chunk("doc-a", "a1", "guide.txt", "first"),
            _chunk("doc-a", "a2", "guide.txt", "second"),
        ],
        [[1.0, 0.0], [0.8, 0.2]],
    )

    assert store.list_documents()[0].chunk_count == 2
    assert store.delete_document("doc-a") is True
    assert store.list_documents() == []
    assert store.search([1.0, 0.0], top_k=3) == []
    assert store.delete_document("doc-a") is False


def test_store_rejects_inconsistent_embedding_dimensions(tmp_path):
    store = SQLiteVectorStore(tmp_path / "vectors.db")
    store.add_document(
        "doc-a", "a.txt", [_chunk("doc-a", "a1", "a.txt", "first")], [[1.0, 0.0]]
    )

    with pytest.raises(StorageError, match="dimensions"):
        store.add_document(
            "doc-b", "b.txt", [_chunk("doc-b", "b1", "b.txt", "second")], [[1.0, 0.0, 0.0]]
        )


def test_store_rejects_query_embedding_with_wrong_dimension(tmp_path):
    store = SQLiteVectorStore(tmp_path / "vectors.db")
    store.add_document(
        "doc-a", "a.txt", [_chunk("doc-a", "a1", "a.txt", "first")], [[1.0, 0.0]]
    )

    with pytest.raises(StorageError, match="dimension"):
        store.search([1.0], top_k=1)


def test_store_rejects_a_different_embedding_model(tmp_path):
    database = tmp_path / "vectors.db"
    store = SQLiteVectorStore(database, embedding_model="embedding-v1")
    store.add_document(
        "doc-a", "a.txt", [_chunk("doc-a", "a1", "a.txt", "first")], [[1.0, 0.0]]
    )

    with pytest.raises(StorageError, match="Use a new database"):
        SQLiteVectorStore(database, embedding_model="embedding-v2")


def test_empty_store_can_be_reconfigured_for_another_embedding_model(tmp_path):
    database = tmp_path / "vectors.db"
    store = SQLiteVectorStore(database, embedding_model="embedding-v1")
    store.add_document(
        "doc-a", "a.txt", [_chunk("doc-a", "a1", "a.txt", "first")], [[1.0, 0.0]]
    )
    store.delete_document("doc-a")

    reconfigured = SQLiteVectorStore(database, embedding_model="embedding-v2")
    reconfigured.add_document(
        "doc-b", "b.txt", [_chunk("doc-b", "b1", "b.txt", "second")], [[1.0, 0.0, 0.0]]
    )

    assert reconfigured.search([1.0, 0.0, 0.0], top_k=1)[0].chunk.document_id == "doc-b"
