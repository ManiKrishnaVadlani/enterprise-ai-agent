"""Small data models shared between ingestion, storage, and the RAG pipeline."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ExtractedPage:
    text: str
    page_number: int | None = None


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    filename: str
    text: str
    page_number: int | None
    ingested_at: datetime


@dataclass(frozen=True)
class SearchResult:
    chunk: DocumentChunk
    score: float


@dataclass(frozen=True)
class DocumentSummary:
    document_id: str
    filename: str
    ingested_at: datetime
    chunk_count: int
