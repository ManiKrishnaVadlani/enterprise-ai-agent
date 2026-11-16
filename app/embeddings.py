"""Interfaces and OpenAI adapter for document and query embeddings."""

import hashlib
import math
from collections import Counter
from typing import Protocol

from app.errors import ProviderConfigurationError, ProviderError
from app.local_text import local_tokens


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one same-dimension vector for every supplied text."""


class LocalEmbeddingProvider:
    """Deterministic feature-hash embeddings for a small, no-cost local demo."""

    def __init__(self, dimensions: int = 384):
        if dimensions < 16:
            raise ValueError("Local embedding dimensions must be at least 16.")
        self.dimensions = dimensions
        self.model_id = f"local-feature-hash-v1-{dimensions}"

    @staticmethod
    def _features(tokens: list[str]) -> Counter[str]:
        features: Counter[str] = Counter(f"unigram:{token}" for token in tokens)
        features.update(
            {f"bigram:{left}:{right}": 0.5 for left, right in zip(tokens, tokens[1:])}
        )
        return features

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for feature, weight in self._features(local_tokens(text)).items():
                digest = hashlib.blake2b(
                    feature.encode("utf-8"), digest_size=8, person=b"rag-demo"
                ).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] & 1 else -1.0
                vector[index] += sign * weight

            magnitude = math.sqrt(sum(value * value for value in vector))
            if magnitude:
                vector = [value / magnitude for value in vector]
            vectors.append(vector)
        return vectors


class OpenAIEmbeddingProvider:
    def __init__(
        self, api_key: str | None, model: str, client=None, batch_size: int = 64
    ):
        self.api_key = api_key
        self.model = model
        self._client = client
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.batch_size = batch_size

    def _get_client(self):
        if not self.api_key:
            raise ProviderConfigurationError(
                "Set OPENAI_API_KEY before uploading documents or asking questions."
            )
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key, timeout=30, max_retries=2)
            except Exception as error:
                raise ProviderConfigurationError(
                    "The OpenAI provider is unavailable; install project requirements."
                ) from error
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            client = self._get_client()
            vectors: list[list[float]] = []
            for start in range(0, len(texts), self.batch_size):
                batch = texts[start : start + self.batch_size]
                response = client.embeddings.create(model=self.model, input=batch)
                batch_vectors = [list(item.embedding) for item in response.data]
                if len(batch_vectors) != len(batch):
                    raise ProviderError(
                        "The embedding provider returned an incomplete batch."
                    )
                if len({len(vector) for vector in batch_vectors}) != 1:
                    raise ProviderError(
                        "The embedding provider returned inconsistent dimensions."
                    )
                vectors.extend(batch_vectors)
            if len({len(vector) for vector in vectors}) != 1:
                raise ProviderError("The embedding provider returned inconsistent dimensions.")
            return vectors
        except (ProviderConfigurationError, ProviderError):
            raise
        except Exception as error:
            raise ProviderError("The embedding provider could not process the request.") from error
