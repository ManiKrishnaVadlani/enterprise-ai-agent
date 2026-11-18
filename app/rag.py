"""Retrieve relevant passages and generate answers with source metadata."""

from dataclasses import dataclass
import re

from app.embeddings import EmbeddingProvider
from app.errors import DocumentNotFoundError, ProviderError
from app.llm import NO_INFORMATION_ANSWER, LanguageModelProvider
from app.models import SearchResult
from app.vector_store import SQLiteVectorStore


NO_DOCUMENTS_ANSWER = "I could not find relevant information in the indexed documents."
_SOURCE_REFERENCE = re.compile(r"\[Source\s+(\d+)(?=\s*(?::|\]))")


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

    def answer(
        self,
        question: str,
        document_id: str | None = None,
        owner_id: str | None = None,
        retrieval_query: str | None = None,
    ) -> Answer:
        documents = (
            self.store.list_documents(owner_id=owner_id)
            if owner_id is not None
            else self.store.list_documents()
        )
        if document_id is not None and all(
            document.document_id != document_id for document in documents
        ):
            if owner_id is not None:
                raise DocumentNotFoundError("The requested document was not found.")
            return Answer(answer=NO_DOCUMENTS_ANSWER, sources=[])
        if not documents:
            return Answer(answer=NO_DOCUMENTS_ANSWER, sources=[])
        try:
            query_vectors = self.embeddings.embed([retrieval_query or question])
            if len(query_vectors) != 1:
                raise ProviderError("The embedding provider returned no query vector.")
            matches = self.store.search(
                query_vectors[0],
                min(self.top_k * 3, 60),
                document_id,
                owner_id,
                min_score=self.min_relevance_score,
            )
        except ProviderError:
            raise

        # Keep this guard as well as the store-side filter so alternate store
        # implementations cannot accidentally send below-threshold passages.
        relevant = []
        seen_passages: set[tuple[str, str]] = set()
        for match in matches:
            if match.score < self.min_relevance_score:
                continue
            normalized_passage = (
                match.chunk.document_id,
                " ".join(match.chunk.text.split()).casefold(),
            )
            if normalized_passage in seen_passages:
                continue
            seen_passages.add(normalized_passage)
            relevant.append(match)
            if len(relevant) >= self.top_k:
                break
        if not relevant:
            return Answer(answer=NO_DOCUMENTS_ANSWER, sources=[])

        context = "\n\n".join(self._format_context(index, match) for index, match in enumerate(relevant, 1))
        generated_answer = self.language_model.generate_answer(question, context).strip()
        if generated_answer == NO_INFORMATION_ANSWER:
            return Answer(answer=NO_INFORMATION_ANSWER, sources=[])

        # Source numbers are the stable provider-facing references. Return only
        # the chunks the answer actually cites, and abstain if references are
        # missing or point outside the supplied evidence.
        source_numbers = list(dict.fromkeys(
            int(number) for number in _SOURCE_REFERENCE.findall(generated_answer)
        ))
        if not source_numbers or any(
            number < 1 or number > len(relevant) for number in source_numbers
        ):
            return Answer(answer=NO_INFORMATION_ANSWER, sources=[])

        citations = [
            Citation(
                document_id=relevant[number - 1].chunk.document_id,
                filename=relevant[number - 1].chunk.filename,
                chunk_id=relevant[number - 1].chunk.chunk_id,
                page_number=relevant[number - 1].chunk.page_number,
                relevance_score=round(relevant[number - 1].score, 4),
            )
            for number in source_numbers
        ]
        return Answer(answer=generated_answer, sources=citations)

    @staticmethod
    def _format_context(index: int, match: SearchResult) -> str:
        page = f", page {match.chunk.page_number}" if match.chunk.page_number else ""
        label = f"[Source {index}: {match.chunk.filename}{page}]"
        return f"{label}\n{match.chunk.text}"
