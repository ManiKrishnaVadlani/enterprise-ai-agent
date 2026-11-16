"""A small persistent SQLite vector store for local and portfolio demos."""

import json
import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.errors import StorageError
from app.models import DocumentChunk, DocumentSummary, SearchResult


class SQLiteVectorStore:
    """Persist chunks and vectors; rank a small corpus with cosine similarity."""

    def __init__(self, database_path: str | Path, embedding_model: str | None = None):
        self.database_path = Path(database_path)
        self.embedding_model = embedding_model
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        """Commit or roll back one operation, then always release its connection."""
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        try:
            with self._session() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        document_id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        ingested_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS chunks (
                        chunk_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL REFERENCES documents(document_id)
                            ON DELETE CASCADE,
                        text TEXT NOT NULL,
                        page_number INTEGER,
                        embedding TEXT NOT NULL,
                        ingested_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_chunks_document_id
                        ON chunks(document_id);
                    CREATE TABLE IF NOT EXISTS store_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    """
                )
                if self.embedding_model:
                    stored_model = connection.execute(
                        "SELECT value FROM store_metadata WHERE key = 'embedding_model'"
                    ).fetchone()
                    existing_vectors = connection.execute(
                        "SELECT 1 FROM chunks LIMIT 1"
                    ).fetchone()
                    if (
                        stored_model
                        and stored_model["value"] != self.embedding_model
                        and existing_vectors
                    ):
                        raise StorageError(
                            "The configured embedding model differs from this vector store. "
                            "Use a new database and re-ingest documents."
                        )
                    if not stored_model:
                        if existing_vectors:
                            raise StorageError(
                                "This vector store has no embedding-model metadata. "
                                "Use a new database and re-ingest documents."
                            )
                        connection.execute(
                            "INSERT INTO store_metadata(key, value) VALUES (?, ?)",
                            ("embedding_model", self.embedding_model),
                        )
                    elif stored_model["value"] != self.embedding_model:
                        connection.execute(
                            "UPDATE store_metadata SET value = ? WHERE key = ?",
                            (self.embedding_model, "embedding_model"),
                        )
                        connection.execute(
                            "DELETE FROM store_metadata WHERE key = 'embedding_dimension'"
                        )
        except sqlite3.Error as error:
            raise StorageError("Could not initialize document storage.") from error

    @staticmethod
    def _validate_vector(vector: list[float]) -> None:
        if not vector or any(not math.isfinite(float(value)) for value in vector):
            raise StorageError("Embeddings must contain finite numeric values.")

    def add_document(
        self, document_id: str, filename: str, chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> None:
        if not chunks or len(chunks) != len(embeddings):
            raise StorageError("Each stored chunk must have exactly one embedding.")
        for vector in embeddings:
            self._validate_vector(vector)
        dimensions = {len(vector) for vector in embeddings}
        if len(dimensions) != 1:
            raise StorageError("Embedding dimensions must be consistent.")
        dimension = dimensions.pop()

        try:
            with self._session() as connection:
                stored_dimension = connection.execute(
                    "SELECT value FROM store_metadata WHERE key = 'embedding_dimension'"
                ).fetchone()
                if stored_dimension and int(stored_dimension["value"]) != dimension:
                    raise StorageError(
                        "Embedding dimensions do not match the existing vector store."
                    )
                connection.execute(
                    "INSERT OR IGNORE INTO store_metadata(key, value) VALUES (?, ?)",
                    ("embedding_dimension", str(dimension)),
                )
                ingested_at = chunks[0].ingested_at.isoformat()
                connection.execute(
                    "INSERT INTO documents(document_id, filename, ingested_at) VALUES (?, ?, ?)",
                    (document_id, filename, ingested_at),
                )
                connection.executemany(
                    """INSERT INTO chunks
                    (chunk_id, document_id, text, page_number, embedding, ingested_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            chunk.chunk_id,
                            document_id,
                            chunk.text,
                            chunk.page_number,
                            json.dumps(vector),
                            chunk.ingested_at.isoformat(),
                        )
                        for chunk, vector in zip(chunks, embeddings, strict=True)
                    ],
                )
        except sqlite3.Error as error:
            raise StorageError("Could not save the document and its chunks.") from error

    def search(
        self, query_vector: list[float], top_k: int, document_id: str | None = None
    ) -> list[SearchResult]:
        self._validate_vector(query_vector)
        if top_k < 1:
            raise ValueError("top_k must be positive")
        try:
            with self._session() as connection:
                if document_id is None:
                    rows = connection.execute(
                        """SELECT c.*, d.filename FROM chunks c
                        JOIN documents d ON d.document_id = c.document_id"""
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """SELECT c.*, d.filename FROM chunks c
                        JOIN documents d ON d.document_id = c.document_id
                        WHERE c.document_id = ?""",
                        (document_id,),
                    ).fetchall()
        except sqlite3.Error as error:
            raise StorageError("Could not search document storage.") from error

        scored: list[SearchResult] = []
        for row in rows:
            vector = json.loads(row["embedding"])
            if len(vector) != len(query_vector):
                raise StorageError("Query embedding dimension does not match stored vectors.")
            score = self._cosine_similarity(query_vector, vector)
            from datetime import datetime

            chunk = DocumentChunk(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                filename=row["filename"],
                text=row["text"],
                page_number=row["page_number"],
                ingested_at=datetime.fromisoformat(row["ingested_at"]),
            )
            scored.append(SearchResult(chunk=chunk, score=score))
        return sorted(scored, key=lambda result: result.score, reverse=True)[:top_k]

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
        right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    def list_documents(self) -> list[DocumentSummary]:
        from datetime import datetime

        try:
            with self._session() as connection:
                rows = connection.execute(
                    """SELECT d.document_id, d.filename, d.ingested_at,
                    COUNT(c.chunk_id) AS chunk_count FROM documents d
                    LEFT JOIN chunks c ON c.document_id = d.document_id
                    GROUP BY d.document_id ORDER BY d.ingested_at DESC"""
                ).fetchall()
        except sqlite3.Error as error:
            raise StorageError("Could not list stored documents.") from error
        return [
            DocumentSummary(
                document_id=row["document_id"],
                filename=row["filename"],
                ingested_at=datetime.fromisoformat(row["ingested_at"]),
                chunk_count=row["chunk_count"],
            )
            for row in rows
        ]

    def delete_document(self, document_id: str) -> bool:
        try:
            with self._session() as connection:
                cursor = connection.execute(
                    "DELETE FROM documents WHERE document_id = ?", (document_id,)
                )
                if cursor.rowcount:
                    remaining = connection.execute(
                        "SELECT 1 FROM chunks LIMIT 1"
                    ).fetchone()
                    if not remaining:
                        connection.execute(
                            "DELETE FROM store_metadata WHERE key = 'embedding_dimension'"
                        )
                return cursor.rowcount > 0
        except sqlite3.Error as error:
            raise StorageError("Could not delete the requested document.") from error

    def check_ready(self) -> bool:
        try:
            with self._session() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error as error:
            raise StorageError("Document storage is not ready.") from error
