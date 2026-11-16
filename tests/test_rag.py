from datetime import datetime, timezone

from app.models import DocumentChunk
from app.rag import NO_DOCUMENTS_ANSWER, RAGPipeline
from app.vector_store import SQLiteVectorStore


class FakeEmbeddings:
    def __init__(self, vector=None):
        self.vector = vector or [1.0, 0.0]
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return [self.vector for _ in texts]


class FakeLanguageModel:
    def __init__(self):
        self.calls = []

    def generate_answer(self, question, context):
        self.calls.append((question, context))
        return "The handbook says to use multifactor authentication. [Source 1]"


def _add_document(store, document_id="doc-a"):
    chunk = DocumentChunk(
        chunk_id="chunk-a",
        document_id=document_id,
        filename="handbook.txt",
        text="Use multifactor authentication for remote access.",
        page_number=2,
        ingested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    store.add_document(document_id, chunk.filename, [chunk], [[1.0, 0.0]])


def test_rag_returns_relevant_answer_with_source_citation_metadata(tmp_path):
    store = SQLiteVectorStore(tmp_path / "rag.db")
    _add_document(store)
    embeddings = FakeEmbeddings()
    language_model = FakeLanguageModel()
    pipeline = RAGPipeline(store, embeddings, language_model, top_k=3)

    result = pipeline.answer("How do I secure remote access?")

    assert result.answer.endswith("[Source 1]")
    assert result.sources[0].document_id == "doc-a"
    assert result.sources[0].filename == "handbook.txt"
    assert result.sources[0].page_number == 2
    assert result.sources[0].relevance_score == 1.0
    assert "[Source 1: handbook.txt, page 2]" in language_model.calls[0][1]


def test_rag_returns_no_documents_message_without_calling_provider(tmp_path):
    store = SQLiteVectorStore(tmp_path / "rag.db")
    language_model = FakeLanguageModel()
    pipeline = RAGPipeline(store, FakeEmbeddings(), language_model)

    result = pipeline.answer("What does the policy say?")

    assert result.answer == NO_DOCUMENTS_ANSWER
    assert result.sources == []
    assert language_model.calls == []


def test_rag_filters_irrelevant_results_and_supports_document_filter(tmp_path):
    store = SQLiteVectorStore(tmp_path / "rag.db")
    _add_document(store)
    language_model = FakeLanguageModel()
    pipeline = RAGPipeline(
        store, FakeEmbeddings([0.0, 1.0]), language_model, min_relevance_score=0.2
    )

    no_match = pipeline.answer("What is in the document?")
    missing_document = pipeline.answer("What is in the document?", "unknown-id")

    assert no_match.answer == NO_DOCUMENTS_ANSWER
    assert missing_document.answer == NO_DOCUMENTS_ANSWER
    assert language_model.calls == []
