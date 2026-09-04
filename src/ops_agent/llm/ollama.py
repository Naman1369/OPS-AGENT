"""Ollama backend -- the local, deterministic fallback named in the synopsis."""

from __future__ import annotations

import json
from typing import Any

from .base import LLMError, LLMProvider


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.1:8b",
        base_url: str = "http://localhost:11434",
        timeout: int = 120,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _complete(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        task: str | None,
    ) -> tuple[str, Any]:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover
            raise LLMError("requests is not installed. Run: pip install requests") from exc

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        try:
            response = requests.post(
                f"{self.base_url}/api/generate", json=payload, timeout=self.timeout
            )
            response.raise_for_status()
            body = response.json()
        except Exception as exc:  # pragma: no cover - network dependent
            raise LLMError(f"Ollama request failed at {self.base_url}: {exc}") from exc

        text = body.get("response", "")
        if not text.strip():
            raise LLMError("Ollama returned an empty response.")
        return text, body
