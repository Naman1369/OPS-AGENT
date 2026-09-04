"""Pluggable LLM backends: Gemini (primary), Ollama (fallback), Mock (offline)."""

from .base import LLMError, LLMProvider, LLMResponse, extract_json
from .factory import get_provider
from .gemini import GeminiProvider
from .mock import MockProvider
from .ollama import OllamaProvider

__all__ = [
    "LLMError",
    "LLMProvider",
    "LLMResponse",
    "extract_json",
    "get_provider",
    "GeminiProvider",
    "MockProvider",
    "OllamaProvider",
]
