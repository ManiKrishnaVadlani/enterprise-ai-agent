from app.config import Settings
from app.embeddings import LocalEmbeddingProvider, OpenAIEmbeddingProvider
from app.llm import ExtractiveAnswerProvider, OpenAILanguageModel
from app.services import build_services


def test_service_builder_uses_local_providers_by_explicit_mode_without_a_key(tmp_path):
    services = build_services(
        Settings(
            ai_mode="local",
            llm_provider="extractive",
            openai_api_key=None,
            database_path=tmp_path / "local.db",
        )
    )

    assert isinstance(services.documents.embeddings, LocalEmbeddingProvider)
    assert isinstance(services.rag.embeddings, LocalEmbeddingProvider)
    assert isinstance(services.rag.language_model, ExtractiveAnswerProvider)
    assert services.store.embedding_model == services.documents.embeddings.model_id


def test_service_builder_preserves_openai_providers_as_an_opt_in_mode(tmp_path):
    services = build_services(
        Settings(
            ai_mode="openai",
            llm_provider="openai",
            openai_api_key=None,
            database_path=tmp_path / "openai.db",
        )
    )

    assert isinstance(services.documents.embeddings, OpenAIEmbeddingProvider)
    assert isinstance(services.rag.language_model, OpenAILanguageModel)
    assert services.store.embedding_model == services.documents.embeddings.model


def test_service_builder_uses_provider_specific_relevance_thresholds(tmp_path):
    local = build_services(
        Settings(
            ai_mode="local",
            local_min_relevance_score=0.27,
            database_path=tmp_path / "local.db",
        )
    )
    openai = build_services(
        Settings(
            ai_mode="openai",
            llm_provider="openai",
            openai_min_relevance_score=0.36,
            database_path=tmp_path / "openai.db",
        )
    )

    assert local.rag.min_relevance_score == 0.27
    assert openai.rag.min_relevance_score == 0.36
