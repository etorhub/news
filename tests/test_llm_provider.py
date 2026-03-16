"""Tests for LLM provider layer."""

from unittest.mock import MagicMock, patch

import pytest

from app.llm.provider import (
    AnthropicProvider,
    GeminiProvider,
    LLMProviderError,
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
