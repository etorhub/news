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


class LocalLLMProvider(LLMProvider):
    """Local LLM via Hugging Face transformers and PyTorch. No API key required."""

    def __init__(
        self,
        model: str,
        model_path: str | None = None,
        device: str = "cpu",
    ) -> None:
        self._model_name = model_path or model
        self._device = device
        self._model: Any = None
        self._tokenizer: Any = None

    def _get_model_and_tokenizer(self) -> tuple[Any, Any]:
        """Lazy-load the model and tokenizer on first use."""
        if self._model is None:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
            self._model = AutoModelForCausalLM.from_pretrained(self._model_name)
            self._model.to(self._device)
        return self._model, self._tokenizer

    def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        try:
            model, tokenizer = self._get_model_and_tokenizer()

            max_length = getattr(
                model.config, "max_position_embeddings", None
            ) or getattr(model.config, "model_max_length", 2048)
            max_input_length = (max_length or 2048) - max_tokens

            # Use chat template if available (instruction-tuned models)
            try:
                messages = [{"role": "user", "content": prompt}]
                input_ids = tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=True,
                    return_tensors="pt",
                ).to(self._device)
            except Exception:
                input_ids = tokenizer(
                    prompt,
                    return_tensors="pt",
                    truncation=True,
                    max_length=max_input_length,
                ).input_ids.to(self._device)

            # Truncate to fit context window
            if input_ids.shape[1] > max_input_length:
                input_ids = input_ids[:, -max_input_length:]

            outputs = model.generate(
                input_ids,
                max_new_tokens=max_tokens,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )

            # Decode only the generated part (exclude input)
            generated_ids = outputs[:, input_ids.shape[1] :]
            text: str = tokenizer.decode(
                generated_ids[0], skip_special_tokens=True
            )
            return text.strip()
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
    if provider_name == "local":
        model_path = llm.get("model_path")
        device = llm.get("device") or "cpu"
        local_model = llm.get("model") or "HuggingFaceH4/zephyr-3b-beta"
        model_or_path = model_path or local_model
        return LocalLLMProvider(
            model=model_or_path,
            model_path=model_path,
            device=device,
        )
    raise LLMProviderError(f"Unknown LLM provider: {provider_name}")
