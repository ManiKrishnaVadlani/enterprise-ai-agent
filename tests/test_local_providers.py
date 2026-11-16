import math

import pytest

from app.embeddings import LocalEmbeddingProvider
from app.llm import ExtractiveAnswerProvider, NO_INFORMATION_ANSWER


def test_local_embeddings_are_deterministic_normalized_and_fixed_dimension():
    provider = LocalEmbeddingProvider()

    first = provider.embed(["Remote access requires multifactor authentication."])[0]
    repeated = provider.embed(["Remote access requires multifactor authentication."])[0]

    assert provider.model_id == "local-feature-hash-v1-384"
    assert len(first) == 384
    assert first == repeated
    assert all(math.isfinite(value) for value in first)
    assert math.sqrt(sum(value * value for value in first)) == pytest.approx(1.0)


def test_local_embeddings_are_case_and_punctuation_insensitive():
    provider = LocalEmbeddingProvider()

    assert provider.embed(["Access policy!"]) == provider.embed(["ACCESS, POLICY"])


def test_local_embeddings_return_a_zero_vector_for_no_content_words():
    provider = LocalEmbeddingProvider(dimensions=32)

    assert provider.embed(["the, and, to!"]) == [[0.0] * 32]


def test_local_embedding_rejects_too_small_dimensions():
    with pytest.raises(ValueError, match="at least 16"):
        LocalEmbeddingProvider(dimensions=8)


def test_extractive_provider_uses_matching_source_sentences_and_cites_them():
    provider = ExtractiveAnswerProvider()
    context = (
        "[Source 1: handbook.txt, page 2]\n"
        "Remote access requires multifactor authentication. Passwords are rotated quarterly.\n\n"
        "[Source 2: unrelated.txt]\nThe cafeteria closes at six."
    )

    answer = provider.generate_answer("How is remote access secured?", context)

    assert answer == (
        "Remote access requires multifactor authentication. "
        "[Source 1: handbook.txt, page 2]"
    )
    assert "cafeteria" not in answer


@pytest.mark.parametrize(
    ("question", "context"),
    [
        ("What is the rule?", "[Source 1: policy.txt]\nThe cafeteria closes at six."),
        ("the and to", "[Source 1: policy.txt]\nRemote access requires MFA."),
        ("Remote access?", ""),
    ],
)
def test_extractive_provider_returns_safe_no_information_without_overlap(
    question, context
):
    assert ExtractiveAnswerProvider().generate_answer(question, context) == (
        NO_INFORMATION_ANSWER
    )


def test_extractive_provider_requires_a_positive_sentence_limit():
    with pytest.raises(ValueError, match="max_sentences"):
        ExtractiveAnswerProvider(max_sentences=0)
