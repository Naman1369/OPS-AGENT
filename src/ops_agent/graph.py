"""The OPS-AGENT LangGraph state graph.

Topology
--------

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
"""

from __future__ import annotations

import time
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from .agents.governance import ESCALATE_TO_HUMAN, SAFE_TO_RESOLVE, governance_node
from .agents.intake import intake_node
from .agents.resolution import resolution_node
from .agents.retrieval import retrieval_node
from .state import OpsAgentState, new_state, trace_event

# Below this, the ticket was not understood well enough to be worth retrieving on.
MIN_INTAKE_CONFIDENCE_FOR_RETRIEVAL = 0.15


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
        f"Confidence: {float(state.get('confidence_score') or 0.0):.2f} "
        f"(raw, uncalibrated)"
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
        # Resolution Agent, so every trace has the same shape for the Week 10-12
        # audit trail and the Week 13-14 evaluation harness.
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
                },
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
        ],
    }


# --------------------------------------------------------------------------- #
# Graph construction
# --------------------------------------------------------------------------- #


def build_graph() -> StateGraph:
    """Assemble the uncompiled state graph."""
    graph = StateGraph(OpsAgentState)

    graph.add_node("intake", intake_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("resolution", resolution_node)
    graph.add_node("governance", governance_node)
    graph.add_node("deliver", deliver_node)
    graph.add_node("escalate", escalate_node)

    graph.add_edge(START, "intake")
    graph.add_conditional_edges(
        "intake", route_after_intake, {"retrieval": "retrieval", "governance": "governance"}
    )
    graph.add_conditional_edges(
        "retrieval", route_after_retrieval, {"resolution": "resolution", "governance": "governance"}
    )
    graph.add_edge("resolution", "governance")
    graph.add_conditional_edges(
        "governance", route_after_governance, {"deliver": "deliver", "escalate": "escalate"}
    )
    graph.add_edge("deliver", END)
    graph.add_edge("escalate", END)

    return graph


def compile_pipeline():
    """Compile the graph into a runnable pipeline."""
    return build_graph().compile()


def run_ticket(
    raw_text: str,
    ticket_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> OpsAgentState:
    """Convenience entry point: run one ticket end to end."""
    pipeline = compile_pipeline()
    return pipeline.invoke(new_state(raw_text, ticket_id=ticket_id, metadata=metadata))


__all__ = [
    "build_graph",
    "compile_pipeline",
    "run_ticket",
    "route_after_intake",
    "route_after_retrieval",
    "route_after_governance",
    "deliver_node",
    "escalate_node",
]
