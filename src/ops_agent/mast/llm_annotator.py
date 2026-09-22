"""LLM-as-a-judge MAST annotator (synopsis Phase 6).

Requires a real model. Validate it against the human double-annotated subset
(``scripts/mast_labeling_kit.py agreement``) BEFORE using it on the remaining
traces - that validation is the whole point of the synopsis' protocol.
"""

from __future__ import annotations

import json
from typing import Any

from ..data.schema import EvalTicket
from ..llm import LLMProvider
from ..prompts import mast as prompt
from .taxonomy import FAILURE_MODES, MODE_CODES


def _mode_block() -> str:
    lines = []
    for mode in FAILURE_MODES:
        lines.append(f"{mode.code} {mode.name} ({mode.category}): {mode.definition}")
    return "\n".join(lines)


def _trace_block(final: dict[str, Any]) -> str:
    lines = []
    for event in final.get("agent_trace") or []:
        payload = json.dumps(event.get("payload") or {}, default=str)[:900]
        lines.append(f"[{event.get('agent')}:{event.get('event')}] {payload}")
    return "\n".join(lines)


def _final_block(final: dict[str, Any]) -> str:
    keys = (
        "category", "priority", "retrieval_query", "citations", "resolution_steps",
        "confidence_score", "calibrated_confidence", "governance_verdict", "escalation_flag", "outcome",
    )
    return json.dumps({key: final.get(key) for key in keys}, default=str, indent=1)


def _gold_block(ticket: EvalTicket | None) -> str:
    if ticket is None:
        return "no gold labels available"
    return json.dumps(
        {
            "gold_category": ticket.gold_category,
            "gold_priority": ticket.gold_priority,
            "gold_doc_id": ticket.gold_doc_id,
            "adversarial_type": ticket.adversarial_type,
            "should_escalate": ticket.should_escalate,
        }
    )


class LLMAnnotator:
    """Label a trace with MAST modes using a language model."""

    version = prompt.PROMPT_VERSION

    def __init__(self, provider: LLMProvider) -> None:
        if getattr(provider, "name", "") == "mock":
            raise ValueError(
                "The MAST LLM annotator needs a real model (set GEMINI_API_KEY or use Ollama); "
                "the deterministic mock has no judgement to validate."
            )
        self.provider = provider

    def annotate(self, final: dict[str, Any], ticket: EvalTicket | None = None) -> dict[str, Any]:
        system = prompt.SYSTEM_PROMPT.format(mode_block=_mode_block())
        user = prompt.USER_TEMPLATE.format(
            ticket_text=final.get("raw_text", ""),
            gold_block=_gold_block(ticket),
            trace_block=_trace_block(final),
            final_block=_final_block(final),
        )
        payload, response = self.provider.generate_json(user, system=system, task="mast")
        raw_labels = payload.get("labels") or {}
        labels = {code: bool(raw_labels.get(code, False)) for code in MODE_CODES}
        return {
            "labels": labels,
            "evidence": payload.get("evidence") or {},
            "annotator": f"llm:{self.provider.name}:{self.provider.model}:{self.version}",
            "input_tokens": getattr(response, "input_tokens", 0),
            "output_tokens": getattr(response, "output_tokens", 0),
        }
