"""Gemini backend -- the primary LLM for OPS-AGENT."""

from __future__ import annotations

from typing import Any

from .base import LLMError, LLMProvider


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash") -> None:
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set; cannot use the Gemini provider.")
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover - depends on install
            raise LLMError(
                "google-generativeai is not installed. Run: pip install google-generativeai"
            ) from exc

        genai.configure(api_key=api_key)
        self._genai = genai
        self.model = model

    def _complete(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        task: str | None,
    ) -> tuple[str, Any]:
        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if json_mode:
            generation_config["response_mime_type"] = "application/json"

        model = self._genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system,
            generation_config=generation_config,
        )
        try:
            response = model.generate_content(prompt)
        except Exception as exc:  # pragma: no cover - network dependent
            raise LLMError(f"Gemini request failed: {exc}") from exc

        text = getattr(response, "text", "") or ""
        if not text.strip():
            raise LLMError("Gemini returned an empty response.")
        return text, response
