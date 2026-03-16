"""Tests for LLM provider layer."""

from unittest.mock import MagicMock, patch

import pytest

from app.llm.provider import (
    AnthropicProvider,
    GeminiProvider,
    LLMProviderError,
    LocalLLMProvider,
    OpenAIProvider,
    get_provider,
)


def test_get_provider_anthropic() -> None:
    """get_provider returns AnthropicProvider for anthropic config."""
    config = {"llm": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"}}
    provider = get_provider(config)
    assert isinstance(provider, AnthropicProvider)
    assert provider._model == "claude-sonnet-4-20250514"


def test_get_provider_openai() -> None:
    """get_provider returns OpenAIProvider for openai config."""
    config = {"llm": {"provider": "openai", "model": "gpt-4o"}}
    provider = get_provider(config)
    assert isinstance(provider, OpenAIProvider)
    assert provider._model == "gpt-4o"


def test_get_provider_gemini() -> None:
    """get_provider returns GeminiProvider for gemini config."""
    config = {"llm": {"provider": "gemini", "model": "gemini-1.5-flash"}}
    provider = get_provider(config)
    assert isinstance(provider, GeminiProvider)
    assert provider._model == "gemini-1.5-flash"


def test_get_provider_local() -> None:
    """get_provider returns LocalLLMProvider for local config."""
    config = {"llm": {"provider": "local", "model": "Qwen/Qwen2.5-1.5B-Instruct"}}
    provider = get_provider(config)
    assert isinstance(provider, LocalLLMProvider)
    assert provider._model_name == "Qwen/Qwen2.5-1.5B-Instruct"
    assert provider._device == "cpu"


def test_get_provider_local_with_model_path() -> None:
    """get_provider uses model_path when set for air-gapped loading."""
    config = {
        "llm": {
            "provider": "local",
            "model": "Qwen/Qwen2.5-1.5B-Instruct",
            "model_path": "/path/to/local/model",
        }
    }
    provider = get_provider(config)
    assert isinstance(provider, LocalLLMProvider)
    assert provider._model_name == "/path/to/local/model"


def test_get_provider_unknown_raises() -> None:
    """get_provider raises LLMProviderError for unknown provider."""
    config = {"llm": {"provider": "unknown"}}
    with pytest.raises(LLMProviderError, match="Unknown LLM provider"):
        get_provider(config)


def test_get_provider_defaults_to_anthropic() -> None:
    """get_provider defaults to anthropic when provider not specified."""
    config = {"llm": {"model": "claude-3-5-sonnet"}}
    provider = get_provider(config)
    assert isinstance(provider, AnthropicProvider)


def test_anthropic_provider_raises_on_missing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AnthropicProvider.complete raises LLMProviderError when API key not set."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = AnthropicProvider(model="claude-sonnet-4-20250514", api_key=None)
    with pytest.raises(LLMProviderError, match="ANTHROPIC_API_KEY not set"):
        provider.complete("Hello")


def test_anthropic_provider_raises_on_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AnthropicProvider.complete raises LLMProviderError on API failure."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def failing_create(*args: object, **kwargs: object) -> None:
        raise Exception("Server error")

    mock_client = MagicMock()
    mock_client.messages.create = failing_create

    with patch("anthropic.Anthropic", return_value=mock_client):
        provider = AnthropicProvider(model="claude-sonnet", api_key="test")
        with pytest.raises(LLMProviderError, match="Server error"):
            provider.complete("Hello")


def test_local_provider_complete() -> None:
    """LocalLLMProvider.complete returns decoded text from mocked model."""
    import torch

    mock_tokenizer = MagicMock()
    mock_tokenizer.apply_chat_template.side_effect = Exception("No chat template")
    mock_tokenizer.eos_token_id = 2

    # tokenizer(prompt, ...) returns BatchEncoding with input_ids
    input_ids = torch.zeros(1, 5, dtype=torch.long)
    mock_tokenizer.return_value = MagicMock(input_ids=input_ids)
    expected = "TITLE:\nTest\n\nSUMMARY:\nOne. Two.\n\nFULL:\nText."
    mock_tokenizer.decode.return_value = expected

    mock_model = MagicMock()
    mock_model.config.max_position_embeddings = 2048
    full_output = torch.zeros(1, 15, dtype=torch.long)

    def generate_side_effect(*args: object, **kwargs: object) -> torch.Tensor:
        return full_output

    mock_model.generate = MagicMock(side_effect=generate_side_effect)

    def mock_get_model_and_tokenizer(self: object) -> tuple[MagicMock, MagicMock]:
        return mock_model, mock_tokenizer

    provider = LocalLLMProvider(model="test-model", model_path=None, device="cpu")
    with patch.object(
        LocalLLMProvider,
        "_get_model_and_tokenizer",
        mock_get_model_and_tokenizer,
    ):
        result = provider.complete("Rewrite this", max_tokens=10)

    assert result == expected


def test_local_provider_raises_on_error() -> None:
    """LocalLLMProvider.complete raises LLMProviderError on inference failure."""

    def raise_oom(self: object) -> None:
        raise Exception("Out of memory")

    provider = LocalLLMProvider(model="test-model", device="cpu")
    with patch.object(
        LocalLLMProvider,
        "_get_model_and_tokenizer",
        raise_oom,
    ):
        with pytest.raises(LLMProviderError, match="Out of memory"):
            provider.complete("Hello")
