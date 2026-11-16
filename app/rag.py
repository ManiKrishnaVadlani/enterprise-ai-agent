"""Retrieve relevant passages and generate answers with source metadata."""

from dataclasses import dataclass

from app.embeddings import EmbeddingProvider
from app.errors import ProviderError
from app.llm import NO_INFORMATION_ANSWER, LanguageModelProvider
from app.models import SearchResult
from app.vector_store import SQLiteVectorStore


NO_DOCUMENTS_ANSWER = "I could not find relevant information in the indexed documents."


@dataclass(frozen=True)
class Citation:
    document_id: str
    filename: str
    chunk_id: str
    page_number: int | None
    relevance_score: float


@dataclass(frozen=True)
class Answer:
    answer: str
    sources: list[Citation]


class RAGPipeline:
    def __init__(
        self,
        store: SQLiteVectorStore,
        embeddings: EmbeddingProvider,
        language_model: LanguageModelProvider,
        top_k: int = 4,
        min_relevance_score: float = 0.15,
    ):
        self.store = store
        self.embeddings = embeddings
        self.language_model = language_model
        self.top_k = top_k
        self.min_relevance_score = min_relevance_score

    def answer(self, question: str, document_id: str | None = None) -> Answer:
        documents = self.store.list_documents()
        if not documents or (
            document_id is not None
            and all(document.document_id != document_id for document in documents)
        ):
            return Answer(answer=NO_DOCUMENTS_ANSWER, sources=[])
        try:
            query_vectors = self.embeddings.embed([question])
            if len(query_vectors) != 1:
                raise ProviderError("The embedding provider returned no query vector.")
            matches = self.store.search(query_vectors[0], self.top_k, document_id)
        except ProviderError:
            raise

        relevant = [match for match in matches if match.score >= self.min_relevance_score]
        if not relevant:
            return Answer(answer=NO_DOCUMENTS_ANSWER, sources=[])

        context = "\n\n".join(self._format_context(index, match) for index, match in enumerate(relevant, 1))
        generated_answer = self.language_model.generate_answer(question, context)
        if generated_answer == NO_INFORMATION_ANSWER:
            return Answer(answer=generated_answer, sources=[])
        citations = [
            Citation(
                document_id=match.chunk.document_id,
                filename=match.chunk.filename,
                chunk_id=match.chunk.chunk_id,
                page_number=match.chunk.page_number,
                relevance_score=round(match.score, 4),
            )
            for match in relevant
        ]
        return Answer(answer=generated_answer, sources=citations)

    @staticmethod
    def _format_context(index: int, match: SearchResult) -> str:
        page = f", page {match.chunk.page_number}" if match.chunk.page_number else ""
        label = f"[Source {index}: {match.chunk.filename}{page}]"
        return f"{label}\n{match.chunk.text}"
