"""Provider-agnostic LLM interface.

Agents depend only on this interface, never on a concrete SDK.  That keeps each
agent independently testable (CLAUDE.md: Modularity) and lets the whole pipeline
run offline against :class:`~ops_agent.llm.mock.MockProvider`.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class LLMError(RuntimeError):
    """Raised when a provider cannot produce a usable response."""


@dataclass
class LLMResponse:
    """A single completion plus the operational metrics the synopsis tracks."""

    text: str
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    token_count: str = "approximate"  # "exact" when the API reported usage
    raw: Any = field(default=None, repr=False)


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model response.

    Small models wrap JSON in prose or code fences; this recovers the object
    rather than failing the whole node on a formatting quirk.
    """
    if not text or not text.strip():
        raise LLMError("empty response from model")

    candidates: list[str] = []
    fenced = _FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)

    for candidate in candidates:
        candidate = candidate.strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fall back to the first balanced {...} block.
        start = candidate.find("{")
        if start == -1:
            continue
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(candidate)):
            char = candidate[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(candidate[start : idx + 1])
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        break
    raise LLMError(f"could not parse JSON from model response: {text[:240]!r}")


class LLMProvider(ABC):
    """Base class every backend implements."""

    name: str = "base"
    model: str = ""
    # Backends that receive real usage figures from their API fill this in.
    last_usage: dict[str, int] = {}

    @abstractmethod
    def _complete(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        task: str | None,
    ) -> tuple[str, Any]:
        """Return ``(text, raw_response)``. Implemented per backend."""

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1536,
        json_mode: bool = False,
        task: str | None = None,
    ) -> LLMResponse:
        """Run one completion and record latency and rough token counts.

        ``task`` is an optional hint (``"intake"``, ``"resolution"``, ...).  Real
        backends ignore it; the deterministic mock uses it to pick a behaviour.
        """
        started = time.perf_counter()
        self.last_usage = {}
        text, raw = self._complete(prompt, system, temperature, max_tokens, json_mode, task)
        latency_ms = (time.perf_counter() - started) * 1000.0

        # Prefer the token counts the API reports (billed output includes any
        # thinking tokens); fall back to a ~4-characters-per-token estimate.
        usage = self.last_usage or {}
        if usage.get("input_tokens"):
            input_tokens = int(usage["input_tokens"])
            output_tokens = int(usage.get("output_tokens", 0)) + int(usage.get("thinking_tokens", 0))
            token_count = "exact"
        else:
            input_tokens = _approx_tokens(prompt) + _approx_tokens(system or "")
            output_tokens = _approx_tokens(text)
            token_count = "approximate"
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            token_count=token_count,
            raw=raw,
        )

    def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1536,
        task: str | None = None,
    ) -> tuple[dict[str, Any], LLMResponse]:
        """Generate and parse a JSON object, returning it with the raw response."""
        response = self.generate(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            task=task,
        )
        return extract_json(response.text), response


def _approx_tokens(text: str) -> int:
    """Cheap token estimate (~4 characters per token) for cost bookkeeping."""
    return max(0, len(text) // 4)
