"""Intake Agent -- raw ticket text into a structured, retrievable record.

First node in the graph. Everything downstream depends on the category, the
keywords and the retrieval query produced here, so this node is defensive: a
malformed model response degrades to a usable record rather than failing the run.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..llm import LLMError, LLMProvider, get_provider
from ..prompts import intake as prompt
from ..state import CATEGORIES, PRIORITIES, OpsAgentState, trace_event

logger = logging.getLogger(__name__)

AGENT_NAME = "intake"


def _coerce_category(value: Any) -> str:
    candidate = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return candidate if candidate in CATEGORIES else "other"


def _coerce_priority(value: Any) -> str:
    candidate = str(value or "").strip().upper()
    return candidate if candidate in PRIORITIES else "P3"


def _coerce_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _coerce_keywords(value: Any, fallback: str) -> list[str]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        value = []
    keywords = [str(item).strip() for item in value if str(item).strip()]
    if keywords:
        return keywords[:12]
    # Degrade to the raw text rather than handing retrieval an empty query.
    return [token for token in fallback.lower().split() if len(token) > 3][:12]


def _coerce_entities(value: Any) -> dict[str, Any]:
    keys = ("operating_system", "application", "device", "network", "error_code")
    source = value if isinstance(value, dict) else {}
    return {key: str(source.get(key, "") or "").strip() for key in keys}


def intake_node(state: OpsAgentState, provider: LLMProvider | None = None) -> dict[str, Any]:
    """LangGraph node: triage one ticket."""
    started = time.perf_counter()
    provider = provider or get_provider()
    ticket_text = state.get("raw_text", "") or ""

    if not ticket_text.strip():
        return {
            "current_agent": AGENT_NAME,
            "category": "other",
            "priority": "P3",
            "keywords": [],
            "entities": _coerce_entities(None),
            "summary": "",
            "retrieval_query": "",
            "intake_confidence": 0.0,
            "errors": ["intake: ticket text was empty"],
            "agent_trace": [
                trace_event(AGENT_NAME, "failed", {"reason": "empty ticket"}, error="empty ticket")
            ],
        }

    try:
        payload, response = provider.generate_json(
            prompt.USER_TEMPLATE.format(ticket_text=ticket_text),
            system=prompt.SYSTEM_PROMPT,
            task=AGENT_NAME,
        )
        error: str | None = None
    except LLMError as exc:
        logger.warning("Intake LLM call failed: %s", exc)
        payload, response, error = {}, None, str(exc)

    category = _coerce_category(payload.get("category"))
    priority = _coerce_priority(payload.get("priority"))
    keywords = _coerce_keywords(payload.get("keywords"), ticket_text)
    entities = _coerce_entities(payload.get("entities"))
    summary = str(payload.get("summary") or ticket_text[:200]).strip()
    confidence = _coerce_confidence(payload.get("confidence"))

    retrieval_query = str(payload.get("retrieval_query") or "").strip()
    if not retrieval_query:
        # Build one from the strongest signals available.
        parts = [value for value in entities.values() if value] + keywords
        retrieval_query = " ".join(dict.fromkeys(parts)) or ticket_text

    # Policy safeguard, independent of the model: security and data-loss tickets
    # are always at least P1, so the Governance Agent's category gate cannot be
    # bypassed by an under-confident triage.
    if category in ("security", "data_loss"):
        priority = "P1"

    latency_ms = (time.perf_counter() - started) * 1000.0
    errors = [f"intake: {error}"] if error else []

    return {
        "current_agent": AGENT_NAME,
        "category": category,
        "priority": priority,
        "keywords": keywords,
        "entities": entities,
        "summary": summary,
        "retrieval_query": retrieval_query,
        "intake_confidence": confidence,
        "errors": errors,
        "agent_trace": [
            trace_event(
                AGENT_NAME,
                "triaged",
                {
                    "prompt_version": prompt.PROMPT_VERSION,
                    "provider": getattr(response, "provider", "unavailable"),
                    "category": category,
                    "priority": priority,
                    "keywords": keywords,
                    "entities": entities,
                    "intake_confidence": confidence,
                    "retrieval_query": retrieval_query,
                    "input_tokens": getattr(response, "input_tokens", 0),
                    "output_tokens": getattr(response, "output_tokens", 0),
                },
                latency_ms=latency_ms,
                error=error,
            )
        ],
    }
