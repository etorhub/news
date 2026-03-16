"""LLM provider abstraction. Use get_provider(); never call SDKs from routes."""

from abc import ABC, abstractmethod
from typing import Any

from app.config import load_config


class LLMProviderError(Exception):
    """Raised when an LLM provider call fails."""


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        """Send prompt to the model and return the generated text."""
        ...


class AnthropicProvider(LLMProvider):
    """Anthropic Claude via the Messages API."""

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self._model = model
        self._api_key = api_key

    def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        import os

        import anthropic

        api_key = self._api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMProviderError("ANTHROPIC_API_KEY not set")
        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            if not response.content:
                raise LLMProviderError("Empty response from Anthropic")
            text_block = response.content[0]
            if hasattr(text_block, "text"):
                return text_block.text
            raise LLMProviderError("Unexpected response format from Anthropic")
        except anthropic.APIError as e:
            raise LLMProviderError(str(e)) from e
        except Exception as e:
            if isinstance(e, LLMProviderError):
                raise
            raise LLMProviderError(str(e)) from e


class OpenAIProvider(LLMProvider):
    """OpenAI GPT via the Chat Completions API."""

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self._model = model
        self._api_key = api_key

    def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        import os

        from openai import OpenAI

        api_key = self._api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMProviderError("OPENAI_API_KEY not set")
        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            choice = response.choices[0] if response.choices else None
            if not choice or not choice.message or not choice.message.content:
                raise LLMProviderError("Empty response from OpenAI")
            return choice.message.content
        except Exception as e:
            if isinstance(e, LLMProviderError):
                raise
            raise LLMProviderError(str(e)) from e


class GeminiProvider(LLMProvider):
    """Google Gemini via the Generative AI API."""

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self._model = model
        self._api_key = api_key

    def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        import os

        import google.generativeai as genai

        api_key = self._api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMProviderError("GEMINI_API_KEY not set")
        try:
            genai.configure(api_key=api_key)  # type: ignore[attr-defined]
            model = genai.GenerativeModel(  # type: ignore[attr-defined]
                self._model,
                generation_config=genai.GenerationConfig(  # type: ignore[attr-defined]
                    max_output_tokens=max_tokens
                ),
            )
            response = model.generate_content(prompt)
            if not response or not response.text:
                raise LLMProviderError("Empty response from Gemini")
            return str(response.text)
        except Exception as e:
            if isinstance(e, LLMProviderError):
                raise
            raise LLMProviderError(str(e)) from e


def get_provider(config: dict[str, Any] | None = None) -> LLMProvider:
    """Return the configured LLM provider."""
    if config is None:
        config = load_config()
    llm = config.get("llm", {})
    provider_name = (llm.get("provider") or "anthropic").lower()
    model = llm.get("model") or "claude-sonnet-4-20250514"
    api_key = llm.get("api_key")

    if provider_name == "anthropic":
        return AnthropicProvider(model=model, api_key=api_key)
    if provider_name == "openai":
        return OpenAIProvider(model=model, api_key=api_key)
    if provider_name == "gemini":
        return GeminiProvider(model=model, api_key=api_key)
    raise LLMProviderError(f"Unknown LLM provider: {provider_name}")
