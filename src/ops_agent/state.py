"""Typed LangGraph state for the OPS-AGENT pipeline.

Design decision (agreed before implementation): a single FLAT ``TypedDict``.
LangGraph merges node return values key-by-key into this object, so a flat
shape keeps reducers simple and keeps ``confidence_score`` and
``escalation_flag`` -- the two fields the governance research hinges on --
at the top level where CLAUDE.md requires them.

Append-only channels (``agent_trace``, ``errors``) use ``operator.add`` so that
each node contributes without clobbering earlier entries.  That append-only
trace is the seed of the Week 10-12 immutable audit trail.
"""

from __future__ import annotations

import operator
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, TypedDict
from uuid import uuid4

# --------------------------------------------------------------------------- #
# Controlled vocabularies
# --------------------------------------------------------------------------- #

Category = Literal[
    "network",
    "access",
    "email",
    "hardware",
    "software",
    "security",
    "data_loss",
    "other",
]

Priority = Literal["P1", "P2", "P3", "P4"]

GovernanceVerdict = Literal["SAFE_TO_RESOLVE", "ESCALATE_TO_HUMAN", "BLOCKED"]

CATEGORIES: tuple[str, ...] = (
    "network",
    "access",
    "email",
    "hardware",
    "software",
    "security",
    "data_loss",
    "other",
)

PRIORITIES: tuple[str, ...] = ("P1", "P2", "P3", "P4")


# --------------------------------------------------------------------------- #
# Nested record types (values inside the flat state, not nested namespaces)
# --------------------------------------------------------------------------- #


class RetrievedDoc(TypedDict, total=False):
    """One knowledge-base passage returned by semantic similarity search."""

    doc_id: str
    title: str
    source: str
    category: str
    content: str
    score: float  # cosine similarity in [0, 1]; higher is more relevant
    rank: int


class TraceEvent(TypedDict, total=False):
    """A single auditable step. Append-only; never mutated in place."""

    agent: str
    event: str
    timestamp: str
    latency_ms: float
    payload: dict[str, Any]
    error: str | None


# --------------------------------------------------------------------------- #
# The pipeline state
# --------------------------------------------------------------------------- #


class OpsAgentState(TypedDict, total=False):
    """State passed between the Intake, Retrieval, Resolution and Governance nodes."""

    # ---- Ticket identity / raw input -------------------------------------- #
    ticket_id: str
    raw_text: str
    submitted_at: str
    metadata: dict[str, Any]

    # ---- Intake Agent output ---------------------------------------------- #
    category: str
    priority: str
    keywords: list[str]
    entities: dict[str, Any]  # operating_system, application, error_code, device, network
    summary: str
    intake_confidence: float
    retrieval_query: str

    # ---- Retrieval Agent output ------------------------------------------- #
    retrieved_docs: list[RetrievedDoc]
    top_relevance: float
    grounded: bool  # True only when usable evidence was retrieved

    # ---- Resolution Agent output ------------------------------------------ #
    draft_solution: str
    resolution_steps: list[str]
    citations: list[str]  # doc_ids actually referenced by the draft solution
    resolution_rationale: str
    confidence_score: float  # RAW, uncalibrated. Week 8-9 will calibrate this.

    # ---- Governance Agent output ------------------------------------------ #
    escalation_flag: bool
    governance_verdict: str  # GovernanceVerdict
    governance_reasons: list[str]
    policy_checks: dict[str, bool]

    # ---- Terminal output --------------------------------------------------- #
    final_response: str
    outcome: str  # "resolved" | "escalated"

    # ---- Cross-cutting bookkeeping ----------------------------------------- #
    current_agent: str
    errors: Annotated[list[str], operator.add]
    agent_trace: Annotated[list[TraceEvent], operator.add]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def utc_now() -> str:
    """ISO-8601 UTC timestamp used throughout the trace."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_state(
    raw_text: str,
    ticket_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> OpsAgentState:
    """Build a fresh state object for one incoming ticket."""
    return OpsAgentState(
        ticket_id=ticket_id or f"TCK-{uuid4().hex[:8].upper()}",
        raw_text=raw_text.strip(),
        submitted_at=utc_now(),
        metadata=metadata or {},
        retrieved_docs=[],
        grounded=False,
        confidence_score=0.0,
        escalation_flag=False,
        governance_reasons=[],
        policy_checks={},
        errors=[],
        agent_trace=[],
    )


def trace_event(
    agent: str,
    event: str,
    payload: dict[str, Any] | None = None,
    latency_ms: float = 0.0,
    error: str | None = None,
) -> TraceEvent:
    """Construct one append-only trace record."""
    return TraceEvent(
        agent=agent,
        event=event,
        timestamp=utc_now(),
        latency_ms=round(latency_ms, 2),
        payload=payload or {},
        error=error,
    )
