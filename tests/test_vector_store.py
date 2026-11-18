import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
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


def test_store_applies_minimum_score_before_top_k(tmp_path):
    store = SQLiteVectorStore(tmp_path / "score-filter.db")
    store.add_document(
        "doc-low",
        "lower-score.txt",
        [_chunk("doc-low", "chunk-low", "lower-score.txt", "below threshold")],
        [[0.6, 0.8]],
    )
    store.add_document(
        "doc-high",
        "higher-score.txt",
        [_chunk("doc-high", "chunk-high", "higher-score.txt", "above threshold")],
        [[0.8, 0.6]],
    )

    results = store.search([1.0, 0.0], top_k=1, min_score=0.7)

    assert [result.chunk.document_id for result in results] == ["doc-high"]
    assert results[0].score == pytest.approx(0.8)


def test_store_rejects_invalid_minimum_score(tmp_path):
    store = SQLiteVectorStore(tmp_path / "score-validation.db")
    with pytest.raises(ValueError, match="min_score"):
        store.search([1.0, 0.0], top_k=1, min_score=float("nan"))


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


def test_fresh_store_creates_versioned_identity_schema_and_constraints(tmp_path):
    database = tmp_path / "fresh.db"
    store = SQLiteVectorStore(database, embedding_model="local-model")
    user = store.create_user("Demo user", user_id="user-1")
    token = "a" * 64
    token_record = store.store_api_token_hash(
        user.user_id, token, label="workstation", token_id="token-1"
    )

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        document_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(documents)")
        }
        document_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(documents)")
        }
        token_indexes = connection.execute("PRAGMA index_list(api_tokens)").fetchall()
        unique_token_hash_index = any(
            index[2]
            and connection.execute(
                f"PRAGMA index_info('{index[1]}')"
            ).fetchone()[2]
            == "token_hash"
            for index in token_indexes
        )
        migration_versions = connection.execute(
            "SELECT version, name FROM schema_migrations"
        ).fetchall()
        assert connection.execute(
            "SELECT token_hash FROM api_tokens WHERE token_id = 'token-1'"
        ).fetchone() == (token,)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO api_tokens
                (token_id, user_id, token_hash, created_at)
                VALUES ('orphan-token', 'missing-user', ?, '2026-01-01T00:00:00+00:00')""",
                ("b" * 64,),
            )

    assert {
        "users", "api_tokens", "documents", "chunks", "store_metadata",
        "conversations", "conversation_messages",
    } <= tables
    assert "owner_id" in document_columns
    assert "idx_documents_owner_id" in document_indexes
    assert any(row[1] == "idx_api_tokens_user_id" for row in token_indexes)
    assert unique_token_hash_index
    assert migration_versions == [
        (1, "add_users_tokens_and_document_ownership"),
        (2, "add_user_owned_conversations"),
    ]
    assert token_record.token_hash == token
    assert store.get_active_user_for_token_hash(token).user_id == "user-1"

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO documents(document_id, filename, ingested_at, owner_id) "
                "VALUES ('orphan-doc', 'orphan.txt', '2026-01-01T00:00:00+00:00', 'missing-user')"
            )


def test_legacy_database_migration_preserves_documents_chunks_and_vectors(tmp_path):
    database = tmp_path / "legacy.db"
    original_chunk = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "filename": "policy.txt",
        "text": "Existing policy text.",
        "page_number": None,
        "embedding": json.dumps([0.6, 0.8]),
        "ingested_at": "2026-01-02T03:04:05+00:00",
    }
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """CREATE TABLE documents (
                document_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            );
            CREATE TABLE chunks (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES documents(document_id)
                    ON DELETE CASCADE,
                text TEXT NOT NULL,
                page_number INTEGER,
                embedding TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            );
            CREATE INDEX idx_chunks_document_id ON chunks(document_id);
            CREATE TABLE store_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);"""
        )
        connection.execute(
            "INSERT INTO documents VALUES (?, ?, ?)",
            ("doc-1", "policy.txt", "2026-01-02T03:04:05+00:00"),
        )
        connection.execute(
            """INSERT INTO chunks
            (chunk_id, document_id, text, page_number, embedding, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            tuple(original_chunk[key] for key in (
                "chunk_id", "document_id", "text", "page_number", "embedding", "ingested_at"
            )),
        )
        connection.executemany(
            "INSERT INTO store_metadata(key, value) VALUES (?, ?)",
            [("embedding_model", "legacy-model"), ("embedding_dimension", "2")],
        )

    store = SQLiteVectorStore(database, embedding_model="legacy-model")
    results = store.search([0.6, 0.8], top_k=1)
    listed = store.list_documents()
    with sqlite3.connect(database) as connection:
        stored_chunk = connection.execute(
            "SELECT chunk_id, document_id, text, page_number, embedding, ingested_at FROM chunks"
        ).fetchone()
        stored_metadata = dict(connection.execute("SELECT key, value FROM store_metadata"))
        owner_id = connection.execute(
            "SELECT owner_id FROM documents WHERE document_id = 'doc-1'"
        ).fetchone()[0]
        version_rows = connection.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall()

    assert stored_chunk == tuple(
        original_chunk[key]
        for key in (
            "chunk_id", "document_id", "text", "page_number", "embedding", "ingested_at"
        )
    )
    assert stored_metadata == {"embedding_model": "legacy-model", "embedding_dimension": "2"}
    assert owner_id is None
    assert version_rows == [(1,), (2,)]
    assert listed[0].owner_id is None
    assert listed[0].chunk_count == 1
    assert results[0].chunk.text == "Existing policy text."
    assert results[0].score == pytest.approx(1.0)

    SQLiteVectorStore(database, embedding_model="legacy-model")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1


def test_owner_scoped_store_operations_and_token_revocation(tmp_path):
    store = SQLiteVectorStore(tmp_path / "owners.db")
    alice = store.create_user("Alice", user_id="alice")
    bob = store.create_user("Bob", user_id="bob")
    plaintext_token = "agent_test_" + ("x" * 48)
    token_hash = hashlib.sha256(plaintext_token.encode("utf-8")).hexdigest()
    token = store.store_api_token_hash(alice.user_id, token_hash, "test token")

    store.add_document(
        "doc-alice", "a.txt", [_chunk("doc-alice", "a1", "a.txt", "alpha")],
        [[1.0, 0.0]], owner_id=alice.user_id,
    )
    store.add_document(
        "doc-bob", "b.txt", [_chunk("doc-bob", "b1", "b.txt", "beta")],
        [[0.0, 1.0]], owner_id=bob.user_id,
    )

    assert [doc.document_id for doc in store.list_documents(owner_id="alice")] == ["doc-alice"]
    assert [result.chunk.document_id for result in store.search(
        [1.0, 0.0], top_k=5, owner_id="bob"
    )] == ["doc-bob"]
    assert store.delete_document("doc-alice", owner_id="bob") is False
    assert store.delete_document("doc-alice", owner_id="alice") is True
    assert store.get_active_user_for_token_hash(token_hash) == alice
    with sqlite3.connect(store.database_path) as connection:
        stored_hash = connection.execute(
            "SELECT token_hash FROM api_tokens WHERE token_id = ?", (token.token_id,)
        ).fetchone()[0]
    assert stored_hash == token_hash
    assert stored_hash != plaintext_token
    assert store.revoke_api_token(token.token_id) is True
    assert store.revoke_api_token(token.token_id) is False
    assert store.get_active_user_for_token_hash(token_hash) is None


def test_token_hash_validation_and_uniqueness(tmp_path):
    store = SQLiteVectorStore(tmp_path / "tokens.db")
    user = store.create_user("Token owner")

    with pytest.raises(ValueError, match="SHA-256"):
        store.store_api_token_hash(user.user_id, "plaintext-token")

    store.store_api_token_hash(user.user_id, "c" * 64)
    with pytest.raises(StorageError, match="store the API token hash"):
        store.store_api_token_hash(user.user_id, "c" * 64)


def test_concurrent_writes_preserve_all_documents(tmp_path):
    store = SQLiteVectorStore(tmp_path / "concurrent.db")

    def add_document(number):
        document_id = f"doc-{number}"
        store.add_document(
            document_id,
            f"{document_id}.txt",
            [_chunk(document_id, f"chunk-{number}", f"{document_id}.txt", "policy")],
            [[1.0, 0.0]],
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(add_document, range(20)))

    assert len(store.list_documents()) == 20
    assert len(store.search([1.0, 0.0], top_k=30)) == 20


def test_new_database_file_is_private_on_posix(tmp_path):
    import os
    import stat

    if os.name != "posix":
        pytest.skip("POSIX file mode bits are not available on this platform")
    database = tmp_path / "private.db"
    SQLiteVectorStore(database)
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
