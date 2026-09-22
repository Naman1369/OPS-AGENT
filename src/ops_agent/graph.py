"""The OPS-AGENT LangGraph state graph.

Topology (calibrated mode; raw mode omits the calibration node)
---------------------------------------------------------------

                       START
                         |
                    [ intake ]
                         |
             route_after_intake
             /                    \\
    (understood)                 (unintelligible)
     [ retrieval ]                      |
          |                             |
   route_after_retrieval                |
    /              \\                    |
(grounded)      (no evidence)           |
[ resolution ]         \\                |
      |                 \\               |
[ calibration ]          \\              |
      |                   \\             |
      +---------------> [ governance ] <+
                             |
                    route_after_governance
                     /                  \\
              [ deliver ]           [ escalate ]
                     \\                  /
                            END

Two structural rules are enforced by the edges themselves, not by convention:

1. The Resolution Agent is unreachable without retrieved evidence. When
   retrieval finds nothing usable, control skips straight to Governance, which
   escalates. This is CLAUDE.md's grounding rule expressed as graph topology,
   so no future prompt change can bypass it.
2. Governance is the only path to a terminal node. Nothing reaches the user
   without passing the gate.

Governance modes
----------------
``raw``         naively governed: G3 reads the raw confidence (Week 5-7).
``calibrated``  G3 reads the temperature-scaled confidence and the
                risk-controlled threshold from a CalibrationProfile.
``auto``        calibrated when a profile exists AND matches the running
                configuration (model, embedder, prompts, knowledge base);
                raw otherwise, with the reason recorded.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from .agents.calibration import calibration_node
from .agents.governance import ESCALATE_TO_HUMAN, SAFE_TO_RESOLVE, governance_node
from .agents.intake import intake_node
from .agents.resolution import resolution_node
from .agents.retrieval import retrieval_node
from .calibration.profile import CalibrationProfile, load_profiles, pipeline_fingerprint, select_profile
from .config import SETTINGS, GovernanceSettings
from .state import OpsAgentState, new_state, trace_event

logger = logging.getLogger(__name__)

# Below this, the ticket was not understood well enough to be worth retrieving on.
MIN_INTAKE_CONFIDENCE_FOR_RETRIEVAL = 0.15

GOVERNANCE_MODES = ("raw", "calibrated", "auto")


# --------------------------------------------------------------------------- #
# Conditional edges
# --------------------------------------------------------------------------- #


def route_after_intake(state: OpsAgentState) -> Literal["retrieval", "governance"]:
    """Skip retrieval when triage produced nothing worth searching on."""
    query = (state.get("retrieval_query") or "").strip()
    confidence = float(state.get("intake_confidence") or 0.0)
    if not query or confidence < MIN_INTAKE_CONFIDENCE_FOR_RETRIEVAL:
        return "governance"
    return "retrieval"


def route_after_retrieval(state: OpsAgentState) -> Literal["resolution", "governance"]:
    """Enforce grounding: no evidence means the Resolution Agent never runs."""
    return "resolution" if state.get("grounded") else "governance"


def route_after_governance(state: OpsAgentState) -> Literal["deliver", "escalate"]:
    """The gate: only a SAFE_TO_RESOLVE verdict reaches the user."""
    verdict = state.get("governance_verdict")
    if verdict == SAFE_TO_RESOLVE and not state.get("escalation_flag"):
        return "deliver"
    return "escalate"


# --------------------------------------------------------------------------- #
# Terminal nodes
# --------------------------------------------------------------------------- #


def _confidence_line(state: OpsAgentState) -> str:
    raw = float(state.get("confidence_score") or 0.0)
    if state.get("confidence_is_calibrated"):
        calibrated = float(state.get("calibrated_confidence") or 0.0)
        return f"Confidence: {calibrated:.2f} calibrated (raw {raw:.2f})"
    return f"Confidence: {raw:.2f} (raw, uncalibrated)"


def deliver_node(state: OpsAgentState) -> dict[str, Any]:
    """Format the approved answer for the requester."""
    started = time.perf_counter()
    steps = state.get("resolution_steps") or []
    numbered = "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))
    citations = ", ".join(state.get("citations") or []) or "none"

    response = (
        f"{state.get('draft_solution', '')}\n\n"
        f"Recommended steps:\n{numbered}\n\n"
        f"Sources: {citations}\n"
        f"{_confidence_line(state)}"
    )

    return {
        "current_agent": "deliver",
        "final_response": response.strip(),
        "outcome": "resolved",
        "agent_trace": [
            trace_event(
                "deliver",
                "delivered",
                {"citations": state.get("citations") or [], "step_count": len(steps)},
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
        ],
    }


def escalate_node(state: OpsAgentState) -> dict[str, Any]:
    """Hand the ticket to a human, with the draft and the reasons attached.

    An escalation that carries the draft answer and the governance reasoning is
    a head start for the engineer; a bare "escalated" is a dead end.
    """
    started = time.perf_counter()
    reasons = state.get("governance_reasons") or ["No reason recorded."]
    reason_lines = "\n".join(f"- {reason}" for reason in reasons)
    draft = (state.get("draft_solution") or "").strip() or "No grounded draft was produced."
    steps = state.get("resolution_steps") or []
    numbered = "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))

    response = (
        f"ESCALATED TO A HUMAN ENGINEER\n"
        f"Ticket: {state.get('ticket_id', 'unknown')} "
        f"({state.get('category', 'other')} / {state.get('priority', 'P3')})\n"
        f"Verdict: {state.get('governance_verdict', ESCALATE_TO_HUMAN)}\n\n"
        f"Why this was not resolved automatically:\n{reason_lines}\n\n"
        f"Draft for the engineer to review:\n{draft}\n"
        f"{numbered}\n\n"
        f"Evidence: {', '.join(doc.get('doc_id', '') for doc in state.get('retrieved_docs') or []) or 'none'}"
    )

    return {
        "current_agent": "escalate",
        "final_response": response.strip(),
        "outcome": "escalated",
        # Guarantee a complete record even when the ticket never reached the
        # Resolution Agent, so every trace has the same shape for the audit
        # trail and the evaluation harness.
        "draft_solution": state.get("draft_solution", ""),
        "resolution_steps": state.get("resolution_steps", []),
        "citations": state.get("citations", []),
        "resolution_rationale": state.get("resolution_rationale", ""),
        "confidence_score": float(state.get("confidence_score") or 0.0),
        "agent_trace": [
            trace_event(
                "escalate",
                "escalated",
                {
                    "verdict": state.get("governance_verdict"),
                    "reasons": reasons,
                    "confidence_score": state.get("confidence_score"),
                    "calibrated_confidence": state.get("calibrated_confidence"),
                },
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
        ],
    }


# --------------------------------------------------------------------------- #
# Graph construction
# --------------------------------------------------------------------------- #


def build_graph(
    mode: str = "raw",
    profile: CalibrationProfile | None = None,
    governance_settings: GovernanceSettings | None = None,
) -> StateGraph:
    """Assemble the uncompiled state graph for one governance mode."""
    if mode not in ("raw", "calibrated"):
        raise ValueError(f"build_graph mode must be 'raw' or 'calibrated', got {mode!r}")
    if mode == "calibrated" and profile is None:
        raise ValueError("calibrated mode requires a CalibrationProfile")
    active_profile = profile if mode == "calibrated" else None

    def _governance(state: OpsAgentState) -> dict[str, Any]:
        return governance_node(state, settings=governance_settings, profile=active_profile)

    graph = StateGraph(OpsAgentState)
    graph.add_node("intake", intake_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("resolution", resolution_node)
    graph.add_node("governance", _governance)
    graph.add_node("deliver", deliver_node)
    graph.add_node("escalate", escalate_node)

    graph.add_edge(START, "intake")
    graph.add_conditional_edges(
        "intake", route_after_intake, {"retrieval": "retrieval", "governance": "governance"}
    )
    graph.add_conditional_edges(
        "retrieval", route_after_retrieval, {"resolution": "resolution", "governance": "governance"}
    )
    if active_profile is not None:

        def _calibration(state: OpsAgentState) -> dict[str, Any]:
            return calibration_node(state, profile=active_profile)

        graph.add_node("calibration", _calibration)
        graph.add_edge("resolution", "calibration")
        graph.add_edge("calibration", "governance")
    else:
        graph.add_edge("resolution", "governance")
    graph.add_conditional_edges(
        "governance", route_after_governance, {"deliver": "deliver", "escalate": "escalate"}
    )
    graph.add_edge("deliver", END)
    graph.add_edge("escalate", END)
    return graph


@dataclass
class GovernanceResolution:
    """Which governance mode a pipeline will run in, and why."""

    mode: str
    profile: CalibrationProfile | None
    note: str


def current_fingerprint() -> dict[str, Any]:
    """Fingerprint of the configuration this process would run with."""
    from .knowledge import get_store
    from .llm import get_provider

    provider = get_provider()
    store = get_store()
    retrieval = SETTINGS.retrieval
    return pipeline_fingerprint(
        provider.name,
        provider.model,
        getattr(store.embedder, "name", "unknown"),
        retrieval.kb_dir,
        retrieval.top_k,
        retrieval.min_relevance,
    )


def resolve_governance(
    mode: str | None = None,
    settings: GovernanceSettings | None = None,
    fingerprint: dict[str, Any] | None = None,
) -> GovernanceResolution:
    """Decide between raw and calibrated governance (see module docstring)."""
    settings = settings or SETTINGS.governance
    requested = (mode or settings.mode or "auto").strip().lower()
    if requested not in GOVERNANCE_MODES:
        raise ValueError(f"governance mode must be one of {GOVERNANCE_MODES}, got {requested!r}")
    if requested == "raw":
        return GovernanceResolution("raw", None, "raw governance requested")

    profiles = load_profiles(settings.calibration_path)
    if not profiles:
        note = f"no calibration profile at {settings.calibration_path}; using raw governance"
        logger.warning(note)
        return GovernanceResolution("raw", None, note)

    try:
        fingerprint = fingerprint or current_fingerprint()
    except Exception as exc:  # store or provider unavailable
        note = f"could not fingerprint the running configuration ({exc}); using raw governance"
        logger.warning(note)
        return GovernanceResolution("raw", None, note)

    profile, mismatches = select_profile(profiles, fingerprint)
    if profile is None:
        detail = "; ".join(f"{pid}: {', '.join(keys)}" for pid, keys in mismatches.items())
        note = (
            "no calibration profile matches the running configuration "
            f"(mismatched keys - {detail}); using raw governance. Re-run scripts/calibrate.py."
        )
        logger.warning(note)
        return GovernanceResolution("raw", None, note)
    return GovernanceResolution("calibrated", profile, f"calibration profile {profile.profile_id} applied")


class Pipeline:
    """A compiled graph plus the governance mode it was built for."""

    def __init__(self, compiled: Any, resolution: GovernanceResolution) -> None:
        self._compiled = compiled
        self.mode = resolution.mode
        self.profile = resolution.profile
        self.note = resolution.note

    def invoke(self, state: OpsAgentState, *args: Any, **kwargs: Any) -> OpsAgentState:
        return self._compiled.invoke(state, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:  # stream, get_graph, ...
        return getattr(self._compiled, name)


def compile_pipeline(
    mode: str | None = None,
    profile: CalibrationProfile | None = None,
    governance_settings: GovernanceSettings | None = None,
) -> Pipeline:
    """Compile the graph. An explicit ``profile`` forces calibrated mode."""
    if profile is not None:
        resolution = GovernanceResolution("calibrated", profile, f"explicit profile {profile.profile_id}")
    else:
        resolution = resolve_governance(mode, governance_settings)
    graph = build_graph(resolution.mode, resolution.profile, governance_settings)
    return Pipeline(graph.compile(), resolution)


def run_ticket(
    raw_text: str,
    ticket_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    pipeline: Pipeline | None = None,
    audit: Any | None = None,
) -> OpsAgentState:
    """Convenience entry point: run one ticket end to end.

    Pass an :class:`ops_agent.audit.AuditLog` as ``audit`` to persist the run
    to the append-only, hash-chained audit trail.
    """
    pipeline = pipeline or compile_pipeline()
    final = pipeline.invoke(new_state(raw_text, ticket_id=ticket_id, metadata=metadata))
    if audit is not None:
        audit.record_run(final, variant=f"multi_agent_{pipeline.mode}", governance_note=pipeline.note)
    return final


__all__ = [
    "GOVERNANCE_MODES",
    "GovernanceResolution",
    "Pipeline",
    "build_graph",
    "compile_pipeline",
    "current_fingerprint",
    "deliver_node",
    "escalate_node",
    "resolve_governance",
    "route_after_governance",
    "route_after_intake",
    "route_after_retrieval",
    "run_ticket",
]
