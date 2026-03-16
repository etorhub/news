"""LLM provider abstraction. Use get_provider(); never call SDKs from routes."""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from app.config import load_config

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Raised when an LLM provider call fails."""


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    def warm_up(self) -> None:  # noqa: B027
        """Pre-load resources before parallel use. No-op for Ollama."""
        pass

    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        """Send prompt to the model and return the generated text."""
        ...


class OllamaProvider(LLMProvider):
    """LLM via Ollama. No API key required. Runs locally or in a dedicated container."""

    def __init__(self, model: str, host: str = "http://ollama:11434") -> None:
        self._model = model
        self._host = host

    def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        import ollama

        try:
            client = ollama.Client(host=self._host)
            response = client.chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": max_tokens},
            )
            message = (
                response.get("message")
                if isinstance(response, dict)
                else getattr(response, "message", None)
            )
            if not message:
                raise LLMProviderError("Empty response from Ollama")
            content = (
                message.get("content")
                if isinstance(message, dict)
                else getattr(message, "content", None)
            )
            if content is None:
                raise LLMProviderError("Empty response from Ollama")
            return str(content).strip()
        except Exception as e:
            if isinstance(e, LLMProviderError):
                raise
            raise LLMProviderError(str(e)) from e


def get_provider(config: dict[str, Any] | None = None) -> LLMProvider:
    """Return the configured LLM provider (Ollama)."""
    if config is None:
        config = load_config()
    llm = config.get("llm", {})
    model = llm.get("model") or "qwen2.5:7b"
    host = llm.get("host") or os.environ.get("OLLAMA_HOST") or "http://ollama:11434"
    return OllamaProvider(model=model, host=host)
