"""A small persistent SQLite vector store for local and portfolio demos."""

import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from app.errors import StorageError
from app.models import (
    ApiTokenRecord,
    DocumentChunk,
    DocumentSummary,
    SearchResult,
    UserRecord,
)


CURRENT_SCHEMA_VERSION = 1


class SQLiteVectorStore:
    """Persist chunks and vectors; rank a small corpus with cosine similarity."""

    def __init__(self, database_path: str | Path, embedding_model: str | None = None):
        self.database_path = Path(database_path)
        self.embedding_model = embedding_model
        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        database_is_new = not self.database_path.exists()
        connection = sqlite3.connect(self.database_path, timeout=10)
        try:
            if database_is_new and os.name == "posix":
                os.chmod(self.database_path, 0o600)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
            return connection
        except Exception:
            connection.close()
            raise

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
                # Include the DDL in the same transaction as the version record so a
                # failed migration can be retried without a partially upgraded schema.
                connection.execute("BEGIN IMMEDIATE")
                statements = (
                    """CREATE TABLE IF NOT EXISTS documents (
                        document_id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        ingested_at TEXT NOT NULL
                    )""",
                    """CREATE TABLE IF NOT EXISTS chunks (
                        chunk_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL REFERENCES documents(document_id)
                            ON DELETE CASCADE,
                        text TEXT NOT NULL,
                        page_number INTEGER,
                        embedding TEXT NOT NULL,
                        ingested_at TEXT NOT NULL
                    )""",
                    """CREATE INDEX IF NOT EXISTS idx_chunks_document_id
                        ON chunks(document_id)""",
                    """CREATE TABLE IF NOT EXISTS store_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )""",
                )
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    )"""
                )
                latest_version = connection.execute(
                    "SELECT MAX(version) AS version FROM schema_migrations"
                ).fetchone()["version"] or 0
                if latest_version > CURRENT_SCHEMA_VERSION:
                    raise StorageError(
                        "The database schema is newer than this application supports."
                    )
                if latest_version < 1:
                    self._migrate_identity_and_ownership(connection)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, name, applied_at) "
                        "VALUES (?, ?, ?)",
                        (
                            1,
                            "add_users_tokens_and_document_ownership",
                            datetime.now(timezone.utc).isoformat(),
                        ),
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
    def _migrate_identity_and_ownership(
        connection: sqlite3.Connection,
    ) -> None:
        connection.execute(
            """CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
            )"""
        )
        connection.execute(
            """CREATE TABLE api_tokens (
                token_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE
                    CHECK (length(token_hash) = 64 AND token_hash NOT GLOB '*[^0-9a-f]*'),
                label TEXT,
                created_at TEXT NOT NULL,
                revoked_at TEXT
            )"""
        )
        document_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(documents)").fetchall()
        }
        if "owner_id" not in document_columns:
            # Nullable preserves existing documents without inventing an owner.
            connection.execute(
                "ALTER TABLE documents ADD COLUMN owner_id TEXT "
                "REFERENCES users(user_id) ON DELETE RESTRICT"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_owner_id ON documents(owner_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_tokens_user_id ON api_tokens(user_id)"
        )

    @staticmethod
    def _validate_token_hash(token_hash: str) -> None:
        if (
            len(token_hash) != 64
            or any(character not in "0123456789abcdef" for character in token_hash)
        ):
            raise ValueError("API token hashes must be lowercase SHA-256 hex digests.")

    def create_user(
        self, display_name: str, user_id: str | None = None
    ) -> UserRecord:
        cleaned_name = display_name.strip()
        if not cleaned_name:
            raise ValueError("Display name must contain non-whitespace text.")
        user_id = user_id or str(uuid4())
        created_at = datetime.now(timezone.utc)
        try:
            with self._session() as connection:
                connection.execute(
                    "INSERT INTO users(user_id, display_name, created_at) VALUES (?, ?, ?)",
                    (user_id, cleaned_name, created_at.isoformat()),
                )
        except sqlite3.Error as error:
            raise StorageError("Could not create the user record.") from error
        return UserRecord(user_id, cleaned_name, created_at, True)

    def store_api_token_hash(
        self,
        user_id: str,
        token_hash: str,
        label: str | None = None,
        token_id: str | None = None,
    ) -> ApiTokenRecord:
        """Persist only a lowercase SHA-256 digest, never the presented token."""
        self._validate_token_hash(token_hash)
        token_id = token_id or str(uuid4())
        cleaned_label = label.strip() if label and label.strip() else None
        created_at = datetime.now(timezone.utc)
        try:
            with self._session() as connection:
                connection.execute(
                    """INSERT INTO api_tokens
                    (token_id, user_id, token_hash, label, created_at)
                    VALUES (?, ?, ?, ?, ?)""",
                    (
                        token_id,
                        user_id,
                        token_hash,
                        cleaned_label,
                        created_at.isoformat(),
                    ),
                )
        except sqlite3.Error as error:
            raise StorageError("Could not store the API token hash.") from error
        return ApiTokenRecord(
            token_id, user_id, token_hash, cleaned_label, created_at, None
        )

    def create_user_with_api_token_hash(
        self,
        display_name: str,
        token_hash: str,
        label: str | None = None,
    ) -> tuple[UserRecord, ApiTokenRecord]:
        """Atomically create a user and persist only the token's SHA-256 digest."""
        cleaned_name = display_name.strip()
        if not cleaned_name:
            raise ValueError("Display name must contain non-whitespace text.")
        self._validate_token_hash(token_hash)
        cleaned_label = label.strip() if label and label.strip() else None
        user_id = str(uuid4())
        token_id = str(uuid4())
        created_at = datetime.now(timezone.utc)
        try:
            with self._session() as connection:
                connection.execute(
                    "INSERT INTO users(user_id, display_name, created_at) VALUES (?, ?, ?)",
                    (user_id, cleaned_name, created_at.isoformat()),
                )
                connection.execute(
                    """INSERT INTO api_tokens
                    (token_id, user_id, token_hash, label, created_at)
                    VALUES (?, ?, ?, ?, ?)""",
                    (
                        token_id,
                        user_id,
                        token_hash,
                        cleaned_label,
                        created_at.isoformat(),
                    ),
                )
        except sqlite3.Error as error:
            raise StorageError("Could not provision the user API token.") from error
        return (
            UserRecord(user_id, cleaned_name, created_at, True),
            ApiTokenRecord(
                token_id, user_id, token_hash, cleaned_label, created_at, None
            ),
        )

    def get_active_user_for_token_hash(
        self, token_hash: str
    ) -> UserRecord | None:
        self._validate_token_hash(token_hash)
        try:
            with self._session() as connection:
                row = connection.execute(
                    """SELECT u.user_id, u.display_name, u.created_at, u.is_active
                    FROM api_tokens AS t JOIN users AS u ON u.user_id = t.user_id
                    WHERE t.token_hash = ? AND t.revoked_at IS NULL AND u.is_active = 1""",
                    (token_hash,),
                ).fetchone()
        except sqlite3.Error as error:
            raise StorageError("Could not look up the API token.") from error
        if row is None:
            return None
        return UserRecord(
            row["user_id"],
            row["display_name"],
            datetime.fromisoformat(row["created_at"]),
            bool(row["is_active"]),
        )

    def revoke_api_token(self, token_id: str) -> bool:
        revoked_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._session() as connection:
                cursor = connection.execute(
                    """UPDATE api_tokens SET revoked_at = ?
                    WHERE token_id = ? AND revoked_at IS NULL""",
                    (revoked_at, token_id),
                )
                return cursor.rowcount > 0
        except sqlite3.Error as error:
            raise StorageError("Could not revoke the API token.") from error

    @staticmethod
    def _validate_vector(vector: list[float]) -> None:
        if not vector or any(not math.isfinite(float(value)) for value in vector):
            raise StorageError("Embeddings must contain finite numeric values.")

    def add_document(
        self, document_id: str, filename: str, chunks: list[DocumentChunk],
        embeddings: list[list[float]], owner_id: str | None = None,
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
                    """INSERT INTO documents
                    (document_id, filename, ingested_at, owner_id) VALUES (?, ?, ?, ?)""",
                    (document_id, filename, ingested_at, owner_id),
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
        self,
        query_vector: list[float],
        top_k: int,
        document_id: str | None = None,
        owner_id: str | None = None,
        min_score: float | None = None,
    ) -> list[SearchResult]:
        self._validate_vector(query_vector)
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if min_score is not None and (
            not math.isfinite(min_score) or not -1 <= min_score <= 1
        ):
            raise ValueError("min_score must be finite and between -1 and 1")
        try:
            with self._session() as connection:
                conditions: list[str] = []
                parameters: list[str] = []
                if document_id is not None:
                    conditions.append("d.document_id = ?")
                    parameters.append(document_id)
                if owner_id is not None:
                    conditions.append("d.owner_id = ?")
                    parameters.append(owner_id)
                where_clause = (
                    f" WHERE {' AND '.join(conditions)}" if conditions else ""
                )
                rows = connection.execute(
                    """SELECT c.*, d.filename FROM chunks c
                    JOIN documents d ON d.document_id = c.document_id"""
                    + where_clause,
                    parameters,
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
        if min_score is not None:
            scored = [result for result in scored if result.score >= min_score]
        return sorted(scored, key=lambda result: result.score, reverse=True)[:top_k]

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
        right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    def list_documents(self, owner_id: str | None = None) -> list[DocumentSummary]:
        try:
            with self._session() as connection:
                where_clause = ""
                parameters: tuple[str, ...] = ()
                if owner_id is not None:
                    where_clause = " WHERE d.owner_id = ?"
                    parameters = (owner_id,)
                rows = connection.execute(
                    """SELECT d.document_id, d.filename, d.ingested_at, d.owner_id,
                    COUNT(c.chunk_id) AS chunk_count FROM documents d
                    LEFT JOIN chunks c ON c.document_id = d.document_id
                    """
                    + where_clause
                    + " GROUP BY d.document_id ORDER BY d.ingested_at DESC",
                    parameters,
                ).fetchall()
        except sqlite3.Error as error:
            raise StorageError("Could not list stored documents.") from error
        return [
            DocumentSummary(
                document_id=row["document_id"],
                filename=row["filename"],
                ingested_at=datetime.fromisoformat(row["ingested_at"]),
                chunk_count=row["chunk_count"],
                owner_id=row["owner_id"],
            )
            for row in rows
        ]

    def delete_document(
        self, document_id: str, owner_id: str | None = None
    ) -> bool:
        try:
            with self._session() as connection:
                cursor = connection.execute(
                    """DELETE FROM documents WHERE document_id = ?
                    AND (? IS NULL OR owner_id = ?)""",
                    (document_id, owner_id, owner_id),
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
