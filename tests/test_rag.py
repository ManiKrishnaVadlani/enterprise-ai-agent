from datetime import datetime, timezone

import pytest

from app.errors import ProviderError
from app.llm import NO_INFORMATION_ANSWER
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


def test_rag_filters_scores_before_top_k_and_only_cites_answer_evidence(tmp_path):
    store = SQLiteVectorStore(tmp_path / "ranked.db")
    for doc_id, filename, text, vector in (
        ("low", "below.txt", "Lower-scoring evidence.", [0.6, 0.8]),
        ("high", "above.txt", "Higher-scoring evidence.", [0.8, 0.6]),
    ):
        chunk = DocumentChunk(
            f"chunk-{doc_id}", doc_id, filename, text, None,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        store.add_document(doc_id, filename, [chunk], [vector])

    class CitingOnlySecondProvider:
        def generate_answer(self, _question, context):
            assert "[Source 1: above.txt]" in context
            assert "below.txt" not in context
            return "Higher-scoring evidence is relevant. [Source 1]"

    result = RAGPipeline(
        store, FakeEmbeddings(), CitingOnlySecondProvider(), top_k=1,
        min_relevance_score=0.7,
    ).answer("What is the evidence?")

    assert result.answer.endswith("[Source 1]")
    assert [source.filename for source in result.sources] == ["above.txt"]
    assert result.sources[0].relevance_score == pytest.approx(0.8)


def test_rag_returns_only_sources_cited_by_the_answer(tmp_path):
    store = SQLiteVectorStore(tmp_path / "cited-only.db")
    for doc_id, filename, vector in (
        ("first", "first.txt", [0.8, 0.6]),
        ("second", "second.txt", [1.0, 0.0]),
    ):
        chunk = DocumentChunk(
            f"chunk-{doc_id}", doc_id, filename, "Supported policy evidence.", None,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        store.add_document(doc_id, filename, [chunk], [vector])

    class CitesSecondProvider:
        def generate_answer(self, _question, context):
            assert "[Source 1: second.txt]" in context
            assert "[Source 2: first.txt]" in context
            return "The policy contains this evidence. [Source 1]"

    result = RAGPipeline(
        store,
        FakeEmbeddings(),
        CitesSecondProvider(),
        top_k=2,
        min_relevance_score=0.1,
    ).answer("What does the policy say?")

    assert [source.filename for source in result.sources] == ["second.txt"]


@pytest.mark.parametrize(
    "answer",
    ["An uncited claim.", "A claim citing [Source 9].", NO_INFORMATION_ANSWER],
)
def test_rag_abstains_when_answer_has_no_valid_evidence_reference(tmp_path, answer):
    store = SQLiteVectorStore(tmp_path / "citation-validation.db")
    _add_document(store)

    class UnreliableCitationProvider:
        def generate_answer(self, _question, _context):
            return answer

    result = RAGPipeline(
        store, FakeEmbeddings(), UnreliableCitationProvider()
    ).answer("How do I secure remote access?")

    assert result.answer == NO_INFORMATION_ANSWER
    assert result.sources == []


def test_rag_propagates_embedding_and_answer_provider_errors(tmp_path):
    store = SQLiteVectorStore(tmp_path / "provider-errors.db")
    _add_document(store)

    class FailingEmbeddings:
        def embed(self, _texts):
            raise ProviderError("embedding unavailable")

    with pytest.raises(ProviderError, match="embedding unavailable"):
        RAGPipeline(store, FailingEmbeddings(), FakeLanguageModel()).answer("question")

    class FailingLanguageModel:
        def generate_answer(self, _question, _context):
            raise ProviderError("answer unavailable")

    with pytest.raises(ProviderError, match="answer unavailable"):
        RAGPipeline(store, FakeEmbeddings(), FailingLanguageModel()).answer("question")
