import pytest

from pyagenthound.llm.providers import LLMUnavailableError, OllamaProvider


def test_ollama_provider_raises_when_unreachable():
    provider = OllamaProvider(base_url="http://127.0.0.1:1", timeout=2.0)

    with pytest.raises(LLMUnavailableError, match="unreachable"):
        provider.complete("system", "user")
