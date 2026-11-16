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
