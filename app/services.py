"""Application service composition for the modular monolith."""

from dataclasses import dataclass
import logging

from app.config import Settings
from app.document_service import DocumentService
from app.embeddings import LocalEmbeddingProvider, OpenAIEmbeddingProvider
from app.llm import ExtractiveAnswerProvider, OllamaLanguageModel, OpenAILanguageModel
from app.rag import RAGPipeline
from app.vector_store import SQLiteVectorStore
from app.agent import AgentOrchestrator
from app.tools import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class ApplicationServices:
    store: SQLiteVectorStore
    documents: DocumentService
    rag: RAGPipeline
    tools: ToolRegistry | None = None
    agent: AgentOrchestrator | None = None


def build_services(settings: Settings) -> ApplicationServices:
    if settings.ai_mode == "local":
        embeddings = LocalEmbeddingProvider()
        embedding_model_id = embeddings.model_id
    else:
        embeddings = OpenAIEmbeddingProvider(
            settings.openai_api_key, settings.embedding_model
        )
        embedding_model_id = settings.embedding_model

    if settings.llm_provider == "extractive":
        language_model = ExtractiveAnswerProvider()
    elif settings.llm_provider == "ollama":
        language_model = OllamaLanguageModel(
            settings.ollama_base_url,
            settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
            temperature=settings.ollama_temperature,
            think=settings.ollama_think,
            num_predict=settings.ollama_num_predict,
            context_length=settings.ollama_context_length,
            max_prompt_chars=settings.ollama_max_prompt_chars,
        )
    else:
        language_model = OpenAILanguageModel(
            settings.openai_api_key, settings.chat_model
        )

    store = SQLiteVectorStore(
        settings.database_path, embedding_model=embedding_model_id
    )
    services = ApplicationServices(
        store=store,
        documents=DocumentService(
            store=store,
            embeddings=embeddings,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            max_upload_bytes=settings.max_upload_bytes,
            max_pdf_pages=settings.max_pdf_pages,
            max_extracted_text_chars=settings.max_extracted_text_chars,
            max_document_chunks=settings.max_document_chunks,
        ),
        rag=RAGPipeline(
            store=store,
            embeddings=embeddings,
            language_model=language_model,
            top_k=settings.top_k,
            min_relevance_score=settings.relevance_threshold_for(settings.ai_mode),
        ),
    )
    services.tools = ToolRegistry(services)
    services.agent = AgentOrchestrator(services.tools, services.rag)
    logger.info(
        "Application providers configured ai_mode=%s embedding_provider=%s answer_provider=%s",
        settings.ai_mode, type(embeddings).__name__, type(language_model).__name__,
    )
    return services
