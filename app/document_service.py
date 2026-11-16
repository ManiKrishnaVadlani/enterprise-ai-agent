"""Validate, extract, chunk, embed, and persist uploaded documents."""

from datetime import datetime, timezone
from uuid import uuid4

from app.chunking import chunk_text
from app.embeddings import EmbeddingProvider
from app.errors import DocumentNotFoundError, InvalidDocumentError
from app.models import DocumentChunk, DocumentSummary
from app.text_extraction import extract_text, validate_filename
from app.vector_store import SQLiteVectorStore


class DocumentService:
    def __init__(
        self,
        store: SQLiteVectorStore,
        embeddings: EmbeddingProvider,
        chunk_size: int,
        chunk_overlap: int,
        max_upload_bytes: int,
    ):
        self.store = store
        self.embeddings = embeddings
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_upload_bytes = max_upload_bytes

    def ingest(self, filename: str, content: bytes) -> DocumentSummary:
        validate_filename(filename)
        if len(content) > self.max_upload_bytes:
            raise InvalidDocumentError(
                f"The document exceeds the {self.max_upload_bytes}-byte upload limit."
            )
        pages = extract_text(filename, content)
        document_id = str(uuid4())
        ingested_at = datetime.now(timezone.utc)
        chunks: list[DocumentChunk] = []
        for page in pages:
            for text in chunk_text(page.text, self.chunk_size, self.chunk_overlap):
                chunks.append(
                    DocumentChunk(
                        chunk_id=str(uuid4()),
                        document_id=document_id,
                        filename=filename,
                        text=text,
                        page_number=page.page_number,
                        ingested_at=ingested_at,
                    )
                )
        vectors = self.embeddings.embed([chunk.text for chunk in chunks])
        self.store.add_document(document_id, filename, chunks, vectors)
        return DocumentSummary(
            document_id=document_id,
            filename=filename,
            ingested_at=ingested_at,
            chunk_count=len(chunks),
        )

    def list_documents(self) -> list[DocumentSummary]:
        return self.store.list_documents()

    def delete_document(self, document_id: str) -> None:
        if not self.store.delete_document(document_id):
            raise DocumentNotFoundError("The requested document was not found.")
