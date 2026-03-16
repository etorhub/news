"""Embedding provider abstraction. Used for article clustering."""

import os
from abc import ABC, abstractmethod
from typing import Any

from app.config import load_config


class EmbeddingProviderError(Exception):
    """Raised when an embedding API call fails."""


class EmbeddingProvider(ABC):
    """Abstract base for embedding providers."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed text and return a vector of floats."""
        ...


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embeddings via Ollama. No API key. Runs locally or in a dedicated container."""

    def __init__(
        self, model: str = "nomic-embed-text", host: str = "http://ollama:11434"
    ) -> None:
        self._model = model
        self._host = host

    def embed(self, text: str) -> list[float]:
        import ollama

        try:
            client = ollama.Client(host=self._host)
            response = client.embed(model=self._model, input=text[:8000])
            embeddings = (
                response.get("embeddings")
                if isinstance(response, dict)
                else getattr(response, "embeddings", None)
            )
            if not embeddings:
                raise EmbeddingProviderError("Empty response from Ollama embeddings")
            return list(embeddings[0])
        except Exception as e:
            if isinstance(e, EmbeddingProviderError):
                raise
            raise EmbeddingProviderError(str(e)) from e


def get_embedding_provider(config: dict[str, Any] | None = None) -> EmbeddingProvider:
    """Return the configured embedding provider (Ollama)."""
    cfg = config or load_config()
    embeddings_cfg = cfg.get("embeddings", {})
    model = embeddings_cfg.get("model") or "nomic-embed-text"
    host = embeddings_cfg.get("host") or os.environ.get("OLLAMA_HOST") or "http://ollama:11434"
    return OllamaEmbeddingProvider(model=model, host=host)
