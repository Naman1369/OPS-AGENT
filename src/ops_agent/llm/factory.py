"""Provider selection with a safe degradation path.

Order of preference follows the synopsis: Gemini is primary, Ollama is the local
fallback, and the deterministic mock is the last resort so that the pipeline is
never hard-blocked by a missing key or an offline machine.
"""

from __future__ import annotations

import logging

from ..config import LLMSettings, SETTINGS
from .base import LLMError, LLMProvider
from .gemini import GeminiProvider
from .mock import MockProvider
from .ollama import OllamaProvider

logger = logging.getLogger(__name__)


def get_provider(settings: LLMSettings | None = None) -> LLMProvider:
    """Return the configured provider, degrading gracefully if it cannot start."""
    settings = settings or SETTINGS.llm
    choice = settings.resolved_provider()

    if choice == "gemini":
        try:
            return GeminiProvider(
                settings.gemini_api_key,
                settings.gemini_model,
                thinking_budget=settings.gemini_thinking_budget,
                thinking_level=settings.gemini_thinking_level,
            )
        except LLMError as exc:
            logger.warning("Gemini unavailable (%s); falling back to Ollama.", exc)
            choice = "ollama"

    if choice == "ollama":
        return OllamaProvider(settings.ollama_model, settings.ollama_base_url)

    if choice != "mock":
        logger.warning("Unknown provider %r; using the deterministic mock.", choice)

    return MockProvider()
