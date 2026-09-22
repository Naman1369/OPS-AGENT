"""Gemini backend -- the primary LLM for OPS-AGENT.

Uses the current Google Gen AI SDK (``pip install google-genai``;
``from google import genai``). The older ``google-generativeai`` package is
legacy and Google recommends migrating off it; it is still accepted as a
fallback so an existing environment keeps working.

Reproducibility settings (what a calibration study needs from its model):
* temperature 0 on models that accept it;
* thinking kept to a minimum - a zero thinking budget on Gemini 2.5 Flash,
  ``thinking_level="low"`` on Gemini 3.x (configurable), so JSON answers are not
  truncated by hidden reasoning tokens and runs are cheaper and more stable;
* real token counts are read from ``usage_metadata`` for the cost metrics.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import LLMError, LLMProvider

logger = logging.getLogger(__name__)


def _is_gemini3(model: str) -> bool:
    return model.strip().lower().startswith("gemini-3")


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        thinking_budget: int | None = 0,
        thinking_level: str | None = "low",
    ) -> None:
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set; cannot use the Gemini provider.")
        self.model = model
        self._thinking_budget = thinking_budget
        self._thinking_level = thinking_level
        self._client = None
        self._legacy = None
        self.last_usage: dict[str, int] = {}

        try:
            from google import genai  # current SDK

            self._client = genai.Client(api_key=api_key)
            self._types = __import__("google.genai.types", fromlist=["types"])
        except ImportError:
            try:
                import google.generativeai as legacy  # pragma: no cover - legacy path
            except ImportError as exc:  # pragma: no cover - depends on install
                raise LLMError(
                    "The Gemini SDK is not installed. Run: pip install google-genai"
                ) from exc
            legacy.configure(api_key=api_key)  # pragma: no cover
            self._legacy = legacy  # pragma: no cover

    # ------------------------------------------------------------------ #

    def _config(self, system: str | None, temperature: float, max_tokens: int, json_mode: bool):
        types = self._types
        kwargs: dict[str, Any] = {"max_output_tokens": max_tokens}
        if system:
            kwargs["system_instruction"] = system
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
        if not _is_gemini3(self.model):
            # Gemini 3 guidance is to leave sampling parameters at their defaults.
            kwargs["temperature"] = temperature
        try:
            if _is_gemini3(self.model) and self._thinking_level:
                kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=self._thinking_level)
            elif "flash" in self.model and self._thinking_budget is not None:
                kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=self._thinking_budget)
        except (TypeError, ValueError, AttributeError) as exc:  # older SDK without the field
            logger.debug("Thinking configuration not supported by this SDK: %s", exc)
        return types.GenerateContentConfig(**kwargs)

    def _complete(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        task: str | None,
    ) -> tuple[str, Any]:
        if self._client is None:  # pragma: no cover - legacy SDK path
            return self._complete_legacy(prompt, system, temperature, max_tokens, json_mode)
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._config(system, temperature, max_tokens, json_mode),
            )
        except Exception as exc:  # pragma: no cover - network dependent
            raise LLMError(f"Gemini request failed: {exc}") from exc

        usage = getattr(response, "usage_metadata", None)
        self.last_usage = {
            "input_tokens": int(getattr(usage, "prompt_token_count", 0) or 0),
            "output_tokens": int(getattr(usage, "candidates_token_count", 0) or 0),
            "thinking_tokens": int(getattr(usage, "thoughts_token_count", 0) or 0),
        }
        text = getattr(response, "text", "") or ""
        if not text.strip():
            raise LLMError("Gemini returned an empty response.")
        return text, response

    def _complete_legacy(self, prompt, system, temperature, max_tokens, json_mode):  # pragma: no cover
        config: dict[str, Any] = {"temperature": temperature, "max_output_tokens": max_tokens}
        if json_mode:
            config["response_mime_type"] = "application/json"
        model = self._legacy.GenerativeModel(
            model_name=self.model, system_instruction=system, generation_config=config
        )
        try:
            response = model.generate_content(prompt)
        except Exception as exc:
            raise LLMError(f"Gemini request failed: {exc}") from exc
        text = getattr(response, "text", "") or ""
        if not text.strip():
            raise LLMError("Gemini returned an empty response.")
        return text, response
