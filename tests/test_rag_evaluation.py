"""Small, deterministic retrieval smoke set for the local demo providers."""

from datetime import datetime, timezone

from app.embeddings import LocalEmbeddingProvider
from app.llm import ExtractiveAnswerProvider
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
        min_relevance_score=0.1,
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

    unsupported = pipeline.answer(
        "What is the office fax number?", owner_id=user.user_id
    )
    assert unsupported.answer == NO_DOCUMENTS_ANSWER
    assert unsupported.sources == []
