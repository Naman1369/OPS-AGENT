"""Resolution Agent -- grounded remediation from retrieved evidence.

Produces the draft solution and the RAW confidence score. That score is
deliberately left uncalibrated at this milestone (CLAUDE.md: no early
optimisation); Week 8-9 inserts temperature scaling between this node and the
Governance Agent without changing either one's interface.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..llm import LLMError, LLMProvider, get_provider
from ..prompts import resolution as prompt
from ..state import OpsAgentState, trace_event

logger = logging.getLogger(__name__)

AGENT_NAME = "resolution"


def _coerce_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def resolution_node(state: OpsAgentState, provider: LLMProvider | None = None) -> dict[str, Any]:
    """LangGraph node: draft a cited remediation and score confidence in it."""
    started = time.perf_counter()
    retrieved_docs = state.get("retrieved_docs") or []

    # Hard grounding guard. The graph should not route here without evidence,
    # but the guard is enforced in the agent too so the rule holds even if this
    # node is called directly in a test or a future variant of the pipeline.
    if not retrieved_docs:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return {
            "current_agent": AGENT_NAME,
            "draft_solution": "",
            "resolution_steps": [],
            "citations": [],
            "resolution_rationale": (
                "No knowledge-base evidence was available, so no grounded resolution "
                "was generated. Grounding is mandatory."
            ),
            "confidence_score": 0.0,
            "errors": ["resolution: refused to generate without retrieved context"],
            "agent_trace": [
                trace_event(
                    AGENT_NAME,
                    "refused_ungrounded",
                    {"prompt_version": prompt.PROMPT_VERSION, "confidence_score": 0.0},
                    latency_ms=latency_ms,
                )
            ],
        }

    provider = provider or get_provider()
    context_block = prompt.format_context_block(retrieved_docs)
    user_prompt = prompt.USER_TEMPLATE.format(
        ticket_text=state.get("raw_text", ""),
        category=state.get("category", "other"),
        priority=state.get("priority", "P3"),
        keywords=", ".join(state.get("keywords") or []),
        context_block=context_block,
    )

    try:
        payload, response = provider.generate_json(
            user_prompt, system=prompt.SYSTEM_PROMPT, task=AGENT_NAME
        )
        error: str | None = None
    except LLMError as exc:
        logger.warning("Resolution LLM call failed: %s", exc)
        payload, response, error = {}, None, str(exc)

    solution = str(payload.get("solution") or "").strip()
    steps = _coerce_str_list(payload.get("steps"))
    rationale = str(payload.get("rationale") or "").strip()
    confidence = _coerce_confidence(payload.get("confidence"))

    # Anti-fabrication check: a citation to a document that was never retrieved
    # is discarded, and the discard is recorded rather than silently swallowed.
    retrieved_ids = {str(doc.get("doc_id")) for doc in retrieved_docs}
    claimed = _coerce_str_list(payload.get("citations"))
    citations = [doc_id for doc_id in claimed if doc_id in retrieved_ids]
    hallucinated = [doc_id for doc_id in claimed if doc_id not in retrieved_ids]

    if hallucinated:
        logger.warning("Resolution cited documents that were not retrieved: %s", hallucinated)
        confidence = 0.0
        error = (error or "") + f" cited non-retrieved documents: {hallucinated}"

    # An empty or step-less answer cannot carry confidence, whatever was reported.
    if not solution or not steps:
        confidence = 0.0

    latency_ms = (time.perf_counter() - started) * 1000.0
    errors: list[str] = []
    if error:
        errors.append(f"resolution: {error.strip()}")

    return {
        "current_agent": AGENT_NAME,
        "draft_solution": solution,
        "resolution_steps": steps,
        "citations": citations,
        "resolution_rationale": rationale,
        "confidence_score": confidence,  # RAW -- calibration is Week 8-9
        "errors": errors,
        "agent_trace": [
            trace_event(
                AGENT_NAME,
                "drafted" if solution else "no_solution",
                {
                    "prompt_version": prompt.PROMPT_VERSION,
                    "provider": getattr(response, "provider", "unavailable"),
                    "evidence_doc_ids": sorted(retrieved_ids),
                    "citations": citations,
                    "hallucinated_citations": hallucinated,
                    "step_count": len(steps),
                    "confidence_score": confidence,
                    "confidence_is_calibrated": False,
                    "input_tokens": getattr(response, "input_tokens", 0),
                    "output_tokens": getattr(response, "output_tokens", 0),
                },
                latency_ms=latency_ms,
                error=error,
            )
        ],
    }
