"""Governance Agent -- deterministic safety and escalation gate.

This is the project's core contribution and it is intentionally NOT an LLM. A
governance decision that must be auditable, reproducible and defensible cannot
rest on a stochastic model whose own confidence is known to be miscalibrated.
Every check here is a pure function of the state, so the same state always
yields the same verdict, and the reason for that verdict is always recorded.

Two modes, differing ONLY in check G3:

* raw (naively governed, the Week 5-7 behaviour): G3 compares the Resolution
  Agent's raw self-reported confidence with the configured threshold (0.70).
* calibrated (Weeks 8-12): G3 compares the temperature-scaled confidence with
  the threshold selected on the calibration split under a risk guarantee. Both
  numbers come from one CalibrationProfile.

Checks G1, G2 and G4-G7 are identical in both modes by construction.
"""

from __future__ import annotations

import time
from typing import Any

from ..calibration.profile import CalibrationProfile
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
    state: OpsAgentState,
    settings: GovernanceSettings | None = None,
    profile: CalibrationProfile | None = None,
) -> dict[str, Any]:
    """LangGraph node: decide whether the draft answer may be returned autonomously.

    ``profile`` switches check G3 to calibrated mode. Everything else is the
    same pure function of the state it has always been.
    """
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

    # -- G3 CONFIDENT -------------------------------------------------------- #
    # The only check that differs between raw and calibrated governance.
    if profile is not None:
        basis = "calibrated"
        if state.get("confidence_is_calibrated"):
            g3_value = float(state.get("calibrated_confidence") or 0.0)
        else:
            # The ungrounded path skips the calibration node; calibrate here so
            # the value G3 judges is always on the same scale as its threshold.
            g3_value = profile.transform(confidence)
        g3_threshold = float(profile.threshold)
    else:
        basis = "raw"
        g3_value = confidence
        g3_threshold = float(settings.confidence_threshold)

    checks["G3_confident"] = g3_value >= g3_threshold
    if not checks["G3_confident"]:
        if basis == "calibrated" and not profile.feasible:
            reasons.append(
                "G3 confident: no threshold could be certified on the calibration split, "
                "so autonomous resolution is disabled (fail closed)."
            )
        else:
            reasons.append(
                f"G3 confident: {basis} confidence {g3_value:.3f} is below the "
                f"threshold of {g3_threshold:.3f}."
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
    update: dict[str, Any] = {
        "current_agent": AGENT_NAME,
        "escalation_flag": escalation_flag,
        "governance_verdict": verdict,
        "governance_reasons": reasons,
        "policy_checks": checks,
        "confidence_basis": basis,
        "confidence_threshold_applied": g3_threshold,
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
                    "confidence_basis": basis,
                    "confidence_is_calibrated": basis == "calibrated",
                    "calibrated_confidence": g3_value if basis == "calibrated" else None,
                    "confidence_threshold": g3_threshold,
                    "calibration_profile_id": profile.profile_id if profile is not None else None,
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
    if basis == "calibrated":
        update["calibrated_confidence"] = g3_value
        update["confidence_is_calibrated"] = True
        update["calibration_profile_id"] = profile.profile_id
    return update
