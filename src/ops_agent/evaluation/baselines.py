"""Baseline pipelines for the comparative evaluation (Weeks 13-14).

V1  single_agent  one model call triages, answers from the top-k passages
                  retrieved with the raw ticket text, and self-reports
                  confidence; the answer is escalated only if that confidence is
                  below the conventional 0.70 threshold. No separate retrieval
                  query, no relevance filter, no citation check, no policy gates.
V2  ungoverned    the four-agent pipeline with the Governance Agent removed:
                  whatever Resolution produces is delivered.

V3 (naively governed) and V4 (calibration governed) are the production graph in
raw and calibrated mode: see ``ops_agent.graph``.

The baselines reuse the production agents and the same LLM provider wherever
the architecture allows, so differences between variants measure architecture
and governance, not incidental implementation differences.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from ..agents.intake import intake_node
from ..agents.resolution import resolution_node
from ..agents.retrieval import retrieval_node
from ..config import SETTINGS, RetrievalSettings
from ..graph import deliver_node, escalate_node, route_after_intake
from ..llm import LLMError, LLMProvider, get_provider
from ..prompts import resolution as resolution_prompt
from ..prompts import single_agent as prompt
from ..state import CATEGORIES, PRIORITIES, OpsAgentState, trace_event

SINGLE_AGENT_THRESHOLD = 0.70


def _clip(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def single_agent_node(
    state: OpsAgentState,
    provider: LLMProvider | None = None,
    store: Any | None = None,
    settings: RetrievalSettings | None = None,
    threshold: float = SINGLE_AGENT_THRESHOLD,
) -> dict[str, Any]:
    """Retrieve with the raw ticket, then triage + answer + self-assess in one call."""
    started = time.perf_counter()
    provider = provider or get_provider()
    settings = settings or SETTINGS.retrieval
    ticket = state.get("raw_text", "") or ""

    if store is None:
        from ..knowledge import get_store

        store = get_store(settings)
    docs = store.similarity_search(ticket, top_k=settings.top_k) if ticket.strip() else []

    user = prompt.USER_TEMPLATE.format(
        ticket_text=ticket, context_block=resolution_prompt.format_context_block(docs)
    )
    error: str | None = None
    try:
        payload, response = provider.generate_json(user, system=prompt.SYSTEM_PROMPT, task="single_agent")
    except LLMError as exc:
        payload, response, error = {}, None, str(exc)

    category = str(payload.get("category") or "other").strip().lower()
    category = category if category in CATEGORIES else "other"
    priority = str(payload.get("priority") or "P3").strip().upper()
    priority = priority if priority in PRIORITIES else "P3"
    solution = str(payload.get("solution") or "").strip()
    steps = _str_list(payload.get("steps"))
    citations = _str_list(payload.get("citations"))  # NOT checked against retrieval: no verifier
    confidence = _clip(payload.get("confidence"))
    retrieved_ids = {str(d.get("doc_id")) for d in docs}
    unverified = [doc for doc in citations if doc not in retrieved_ids]

    self_safe = bool(solution and steps) and confidence >= threshold
    verdict = "SELF_ASSESSED_SAFE" if self_safe else "SELF_ASSESSED_ESCALATE"
    reasons = (
        [f"Self-reported confidence {confidence:.2f} is at or above {threshold:.2f}."]
        if self_safe
        else [f"Self-reported confidence {confidence:.2f} is below {threshold:.2f} (or no answer)."]
    )
    top = max((float(d.get("score", 0.0)) for d in docs), default=0.0)
    latency_ms = (time.perf_counter() - started) * 1000.0
    return {
        "current_agent": "single_agent",
        "category": category,
        "priority": priority,
        "keywords": [],
        "entities": {},
        "retrieval_query": ticket,
        "intake_confidence": 1.0,
        "retrieved_docs": docs,
        "top_relevance": round(top, 4),
        "grounded": bool(docs),
        "draft_solution": solution,
        "resolution_steps": steps,
        "citations": citations,
        "resolution_rationale": str(payload.get("rationale") or ""),
        "confidence_score": confidence,
        "escalation_flag": not self_safe,
        "governance_verdict": verdict,
        "governance_reasons": reasons,
        "policy_checks": {"self_confidence": self_safe},
        "confidence_basis": "raw",
        "confidence_threshold_applied": threshold,
        "errors": [f"single_agent: {error}"] if error else [],
        "agent_trace": [
            trace_event(
                "single_agent",
                "answered" if solution else "no_solution",
                {
                    "prompt_version": prompt.PROMPT_VERSION,
                    "provider": getattr(response, "provider", "unavailable"),
                    "query": ticket,
                    "doc_ids": sorted(retrieved_ids),
                    "scores": [d.get("score") for d in docs],
                    "citations": citations,
                    "unverified_citations": unverified,
                    "confidence_score": confidence,
                    "confidence_is_calibrated": False,
                    "self_assessed_safe": self_safe,
                    "input_tokens": getattr(response, "input_tokens", 0),
                    "output_tokens": getattr(response, "output_tokens", 0),
                },
                latency_ms=latency_ms,
                error=error,
            )
        ],
    }


def _route_single(state: OpsAgentState) -> Literal["deliver", "escalate"]:
    return "escalate" if state.get("escalation_flag") else "deliver"


def build_single_agent_graph(
    provider: LLMProvider | None = None,
    store: Any | None = None,
    settings: RetrievalSettings | None = None,
    threshold: float = SINGLE_AGENT_THRESHOLD,
) -> StateGraph:
    def _node(state: OpsAgentState) -> dict[str, Any]:
        return single_agent_node(state, provider=provider, store=store, settings=settings, threshold=threshold)

    graph = StateGraph(OpsAgentState)
    graph.add_node("single_agent", _node)
    graph.add_node("deliver", deliver_node)
    graph.add_node("escalate", escalate_node)
    graph.add_edge(START, "single_agent")
    graph.add_conditional_edges("single_agent", _route_single, {"deliver": "deliver", "escalate": "escalate"})
    graph.add_edge("deliver", END)
    graph.add_edge("escalate", END)
    return graph


def _route_ungoverned_retrieval(state: OpsAgentState) -> Literal["resolution", "deliver"]:
    # Grounding is still enforced (the Resolution Agent refuses without
    # evidence) but nothing gates delivery, so an empty answer reaches the user.
    return "resolution" if state.get("grounded") else "deliver"


def _route_ungoverned_intake(state: OpsAgentState) -> Literal["retrieval", "deliver"]:
    return "retrieval" if route_after_intake(state) == "retrieval" else "deliver"


def _mark_ungoverned(state: OpsAgentState) -> dict[str, Any]:
    return {
        "governance_verdict": "UNGOVERNED",
        "escalation_flag": False,
        "governance_reasons": ["No governance layer in this variant."],
        "policy_checks": {},
        "confidence_basis": "raw",
    }


def build_ungoverned_graph() -> StateGraph:
    """Intake -> Retrieval -> Resolution -> Deliver, with no gate."""

    def _deliver(state: OpsAgentState) -> dict[str, Any]:
        update = deliver_node(state)
        update.update(_mark_ungoverned(state))
        return update

    graph = StateGraph(OpsAgentState)
    graph.add_node("intake", intake_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("resolution", resolution_node)
    graph.add_node("deliver", _deliver)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", _route_ungoverned_intake, {"retrieval": "retrieval", "deliver": "deliver"})
    graph.add_conditional_edges(
        "retrieval", _route_ungoverned_retrieval, {"resolution": "resolution", "deliver": "deliver"}
    )
    graph.add_edge("resolution", "deliver")
    graph.add_edge("deliver", END)
    return graph
