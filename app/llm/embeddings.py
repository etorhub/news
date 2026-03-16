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
            # sentence-transformers truncates to model max length internally
            vector = model.encode(text[:8000], convert_to_numpy=True)
            return vector.tolist()
        except Exception as e:
            if isinstance(e, EmbeddingProviderError):
                raise
            raise EmbeddingProviderError(str(e)) from e


def get_embedding_provider(config: dict[str, Any] | None = None) -> EmbeddingProvider:
    """Return the configured embedding provider (local sentence-transformers)."""
    from app.config import load_config

    cfg = config or load_config()
    embeddings_cfg = cfg.get("embeddings", {})
    model = embeddings_cfg.get("model") or "paraphrase-multilingual-MiniLM-L12-v2"
    return LocalEmbeddingProvider(model=model)
