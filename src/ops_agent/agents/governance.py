"""Governance Agent -- deterministic safety and escalation gate.

This is the project's core contribution and it is intentionally NOT an LLM. A
governance decision that must be auditable, reproducible and defensible cannot
rest on a stochastic model whose own confidence is known to be miscalibrated.
Every check here is a pure function of the state, so the same state always
yields the same verdict, and the reason for that verdict is always recorded.

Week 5-7 scope: check G3 reads the RAW confidence emitted by the Resolution
Agent. Week 8-9 replaces the value it reads with a calibrated one; the check
itself, and every other check, is unchanged by that work.
"""

from __future__ import annotations

import time
from typing import Any

from ..config import GovernanceSettings, SETTINGS
from ..prompts import governance as policy
from ..state import OpsAgentState, trace_event

AGENT_NAME = "governance"

SAFE_TO_RESOLVE = "SAFE_TO_RESOLVE"
ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"
BLOCKED = "BLOCKED"

# Intake below this is treated as "the ticket was never understood".
MIN_INTAKE_CONFIDENCE = 0.30


def governance_node(
    state: OpsAgentState, settings: GovernanceSettings | None = None
) -> dict[str, Any]:
    """LangGraph node: decide whether the draft answer may be returned autonomously."""
    started = time.perf_counter()
    settings = settings or SETTINGS.governance

    retrieved_docs = state.get("retrieved_docs") or []
    retrieved_ids = {str(doc.get("doc_id")) for doc in retrieved_docs}
    citations = [str(item) for item in (state.get("citations") or [])]
    steps = state.get("resolution_steps") or []
    solution = (state.get("draft_solution") or "").strip()
    confidence = float(state.get("confidence_score") or 0.0)
    intake_confidence = float(state.get("intake_confidence") or 0.0)
    category = str(state.get("category") or "other")
    priority = str(state.get("priority") or "P3")
    top_relevance = float(state.get("top_relevance") or 0.0)

    checks: dict[str, bool] = {}
    reasons: list[str] = []

    # -- G1 GROUNDED ------------------------------------------------------- #
    checks["G1_grounded"] = bool(state.get("grounded")) and bool(retrieved_docs)
    if not checks["G1_grounded"]:
        reasons.append("G1 grounded: no knowledge-base evidence met the relevance threshold.")

    # -- G2 CITED ---------------------------------------------------------- #
    valid_citations = [doc_id for doc_id in citations if doc_id in retrieved_ids]
    unsupported = [doc_id for doc_id in citations if doc_id not in retrieved_ids]
    checks["G2_cited"] = len(valid_citations) >= settings.min_citations and not unsupported
    if unsupported:
        reasons.append(
            f"G2 cited: resolution cited documents that were never retrieved ({unsupported})."
        )
    elif len(valid_citations) < settings.min_citations:
        reasons.append(
            f"G2 cited: {len(valid_citations)} citation(s) present, "
            f"{settings.min_citations} required."
        )

    # -- G3 CONFIDENT (raw confidence at this milestone) -------------------- #
    checks["G3_confident"] = confidence >= settings.confidence_threshold
    if not checks["G3_confident"]:
        reasons.append(
            f"G3 confident: raw confidence {confidence:.2f} is below the "
            f"threshold of {settings.confidence_threshold:.2f}."
        )

    # -- G4 COMPLETE -------------------------------------------------------- #
    checks["G4_complete"] = bool(solution) and bool(steps)
    if not checks["G4_complete"]:
        reasons.append("G4 complete: the resolution is missing a solution or actionable steps.")

    # -- G5 PRIORITY GATE --------------------------------------------------- #
    checks["G5_priority_gate"] = priority not in settings.always_escalate_priorities
    if not checks["G5_priority_gate"]:
        reasons.append(
            f"G5 priority gate: {priority} incidents always require human review."
        )

    # -- G6 CATEGORY GATE --------------------------------------------------- #
    checks["G6_category_gate"] = category not in settings.always_escalate_categories
    if not checks["G6_category_gate"]:
        reasons.append(
            f"G6 category gate: '{category}' incidents always require human review."
        )

    # -- G7 INTAKE CLARITY --------------------------------------------------- #
    checks["G7_intake_clarity"] = intake_confidence >= MIN_INTAKE_CONFIDENCE
    if not checks["G7_intake_clarity"]:
        reasons.append(
            f"G7 intake clarity: intake confidence {intake_confidence:.2f} indicates the "
            f"ticket was too ambiguous to answer autonomously."
        )

    # -- Verdict ------------------------------------------------------------ #
    pipeline_errored = bool(state.get("errors"))
    if not solution and (pipeline_errored or not checks["G1_grounded"]):
        verdict = BLOCKED
        if pipeline_errored and "BLOCKED" not in " ".join(reasons):
            reasons.append("Pipeline reported errors before a resolution was produced.")
    elif all(checks.values()):
        verdict = SAFE_TO_RESOLVE
    else:
        verdict = ESCALATE_TO_HUMAN

    escalation_flag = verdict != SAFE_TO_RESOLVE
    if not escalation_flag:
        reasons.append("All governance checks passed; safe to resolve autonomously.")

    latency_ms = (time.perf_counter() - started) * 1000.0
    return {
        "current_agent": AGENT_NAME,
        "escalation_flag": escalation_flag,
        "governance_verdict": verdict,
        "governance_reasons": reasons,
        "policy_checks": checks,
        "agent_trace": [
            trace_event(
                AGENT_NAME,
                "decided",
                {
                    "policy_version": policy.PROMPT_VERSION,
                    "verdict": verdict,
                    "escalation_flag": escalation_flag,
                    "checks": checks,
                    "reasons": reasons,
                    "confidence_score": confidence,
                    "confidence_is_calibrated": False,
                    "confidence_threshold": settings.confidence_threshold,
                    "intake_confidence": intake_confidence,
                    "top_relevance": top_relevance,
                    "category": category,
                    "priority": priority,
                    "evidence_doc_ids": sorted(retrieved_ids),
                    "citations": valid_citations,
                },
                latency_ms=latency_ms,
            )
        ],
    }
