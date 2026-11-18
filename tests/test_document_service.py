import pytest

from app.document_service import DocumentService
from app.errors import InvalidDocumentError
from app.vector_store import SQLiteVectorStore


class FixedEmbeddingProvider:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def test_document_service_ingests_lists_and_deletes_text_document(tmp_path):
    store = SQLiteVectorStore(tmp_path / "documents.db")
    service = DocumentService(
        store, FixedEmbeddingProvider(), chunk_size=12, chunk_overlap=3,
        max_upload_bytes=1000,
    )

    document = service.ingest("policy.txt", b"alpha beta gamma delta")

    assert document.filename == "policy.txt"
    assert document.chunk_count == 3
    assert service.list_documents() == [document]
    service.delete_document(document.document_id)
    assert service.list_documents() == []


def test_document_service_enforces_max_upload_size_before_extraction(tmp_path):
    service = DocumentService(
        SQLiteVectorStore(tmp_path / "documents.db"),
        FixedEmbeddingProvider(),
        chunk_size=10,
        chunk_overlap=2,
        max_upload_bytes=3,
    )

    try:
        service.ingest("too-big.txt", b"four")
    except InvalidDocumentError as error:
        assert "upload limit" in str(error)
    else:
        raise AssertionError("Oversized documents must be rejected")


def test_document_service_failed_embedding_leaves_no_document_or_chunks(tmp_path):
    class BrokenEmbeddingProvider:
        def embed(self, texts):
            raise RuntimeError("provider failed")

    store = SQLiteVectorStore(tmp_path / "failed-ingestion.db")
    service = DocumentService(
        store, BrokenEmbeddingProvider(), chunk_size=30, chunk_overlap=4,
        max_upload_bytes=1000,
    )

    try:
        service.ingest("policy.txt", b"A valid policy paragraph.", owner_id="owner-1")
    except RuntimeError as error:
        assert str(error) == "provider failed"
    else:
        raise AssertionError("Embedding failures should stop document ingestion")

    assert store.list_documents(owner_id="owner-1") == []
    assert store.list_documents() == []


def test_document_service_rejects_empty_cleaned_text_before_storage(tmp_path):
    store = SQLiteVectorStore(tmp_path / "empty-ingestion.db")
    service = DocumentService(
        store, FixedEmbeddingProvider(), chunk_size=30, chunk_overlap=4,
        max_upload_bytes=1000,
    )

    try:
        service.ingest("empty.txt", b" \t\n\r\n")
    except InvalidDocumentError as error:
        assert "no extractable text" in str(error)
    else:
        raise AssertionError("Blank documents should not be persisted")

    assert store.list_documents() == []


def test_document_service_stops_before_embedding_when_chunk_cap_is_exceeded(tmp_path):
    class RecordingEmbeddings:
        called = False

        def embed(self, texts):
            self.called = True
            return [[1.0, 0.0] for _ in texts]

    embeddings = RecordingEmbeddings()
    store = SQLiteVectorStore(tmp_path / "chunk-cap.db")
    service = DocumentService(
        store, embeddings, chunk_size=5, chunk_overlap=0,
        max_upload_bytes=1000, max_document_chunks=2,
    )

    with pytest.raises(InvalidDocumentError, match="too many chunks"):
        service.ingest("many.txt", b"one two three four five six", owner_id="owner-1")

    assert not embeddings.called
    assert store.list_documents() == []
