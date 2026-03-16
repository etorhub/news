"""Embedding provider abstraction. Used for article clustering."""

from abc import ABC, abstractmethod
from typing import Any


class EmbeddingProviderError(Exception):
    """Raised when an embedding API call fails."""


class EmbeddingProvider(ABC):
    """Abstract base for embedding providers."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed text and return a vector of floats."""
        ...


class LocalEmbeddingProvider(EmbeddingProvider):
    """Local embeddings via sentence-transformers. No API key required."""

    def __init__(self, model: str = "paraphrase-multilingual-MiniLM-L12-v2") -> None:
        self._model_name = model
        self._model: Any = None

    def _get_model(self) -> Any:
        """Lazy-load the model on first use."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        try:
            model = self._get_model()
            # sentence-transformers truncates to model max length (512 for MiniLM) internally
            vector = model.encode(text[:8000], convert_to_numpy=True)
            return vector.tolist()
        except Exception as e:
            if isinstance(e, EmbeddingProviderError):
                raise
            raise EmbeddingProviderError(str(e)) from e


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI text-embedding-3-small."""

    def __init__(self, model: str = "text-embedding-3-small", api_key: str | None = None) -> None:
        self._model = model
        self._api_key = api_key

    def embed(self, text: str) -> list[float]:
        import os

        from openai import OpenAI

        api_key = self._api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EmbeddingProviderError("OPENAI_API_KEY not set")
        try:
            client = OpenAI(api_key=api_key)
            response = client.embeddings.create(
                input=text[:8000],  # ~6k tokens, stay within limits
                model=self._model,
            )
            if not response.data:
                raise EmbeddingProviderError("Empty response from OpenAI")
            return response.data[0].embedding
        except Exception as e:
            if isinstance(e, EmbeddingProviderError):
                raise
            raise EmbeddingProviderError(str(e)) from e


def get_embedding_provider(config: dict[str, Any] | None = None) -> EmbeddingProvider:
    """Return the configured embedding provider."""
    from app.config import load_config

    cfg = config or load_config()
    embeddings_cfg = cfg.get("embeddings", {})
    provider_name = (embeddings_cfg.get("provider") or "local").lower()
    model = embeddings_cfg.get("model")
    api_key = embeddings_cfg.get("api_key")

    if provider_name == "local":
        model = model or "paraphrase-multilingual-MiniLM-L12-v2"
        return LocalEmbeddingProvider(model=model)
    if provider_name == "openai":
        model = model or "text-embedding-3-small"
        return OpenAIEmbeddingProvider(model=model, api_key=api_key)
    raise EmbeddingProviderError(f"Unknown embedding provider: {provider_name}")
