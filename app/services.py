"""Application service composition for the modular monolith."""

from dataclasses import dataclass

from app.config import Settings
from app.document_service import DocumentService
from app.embeddings import LocalEmbeddingProvider, OpenAIEmbeddingProvider
from app.llm import ExtractiveAnswerProvider, OpenAILanguageModel
from app.rag import RAGPipeline
from app.vector_store import SQLiteVectorStore


@dataclass
class ApplicationServices:
    store: SQLiteVectorStore
    documents: DocumentService
    rag: RAGPipeline


def build_services(settings: Settings) -> ApplicationServices:
    if settings.ai_mode == "local":
        embeddings = LocalEmbeddingProvider()
        language_model = ExtractiveAnswerProvider()
        embedding_model_id = embeddings.model_id
    else:
        embeddings = OpenAIEmbeddingProvider(
            settings.openai_api_key, settings.embedding_model
        )
        language_model = OpenAILanguageModel(
            settings.openai_api_key, settings.chat_model
        )
        embedding_model_id = settings.embedding_model

    store = SQLiteVectorStore(
        settings.database_path, embedding_model=embedding_model_id
    )
    return ApplicationServices(
        store=store,
        documents=DocumentService(
            store=store,
            embeddings=embeddings,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            max_upload_bytes=settings.max_upload_bytes,
            max_pdf_pages=settings.max_pdf_pages,
            max_extracted_text_chars=settings.max_extracted_text_chars,
        ),
        rag=RAGPipeline(
            store=store,
            embeddings=embeddings,
            language_model=language_model,
            top_k=settings.top_k,
            min_relevance_score=settings.min_relevance_score,
        ),
    )
