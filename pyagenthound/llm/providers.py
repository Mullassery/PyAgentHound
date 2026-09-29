"""LLM provider abstraction. See docs/architecture.md section 16.

Provider-neutral by design (product spec sections 1/25): `LLMProvider` is a small
Protocol any backend can implement. Only `OllamaProvider` is implemented today —
local, no API key, no network egress beyond localhost, matching "local-first
development should be possible." OpenAI/Anthropic providers would implement the same
Protocol; not built yet — there's no way to verify them without paid API keys in
this environment, and an untested provider implementation would be worse than none
(see ROADMAP_HONEST.md).
"""

from __future__ import annotations

from typing import Protocol

import requests


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str:
        """Return the raw text completion for a system+user prompt pair."""
        ...


class LLMUnavailableError(RuntimeError):
    """Raised when the configured provider can't be reached or returns nothing."""


class OllamaProvider:
    """Talks to a local Ollama instance (https://ollama.com) over its HTTP API."""

    name = "ollama"

    def __init__(
        self,
        model: str = "qwen2.5:7b-instruct",
        base_url: str = "http://localhost:11434",
        timeout: float = 60.0,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "format": "json",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise LLMUnavailableError(f"Ollama at {self.base_url} unreachable: {exc}") from exc

        content = resp.json().get("message", {}).get("content")
        if not content:
            raise LLMUnavailableError(f"Ollama returned no content: {resp.text!r}")
        return content
