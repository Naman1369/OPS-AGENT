"""Deterministic MAST annotator: the operationalised detectors (Weeks 10-12).

Each detector reads the final state (which carries the full append-only trace)
and, where the mode depends on what the right answer was, the ticket's gold
labels. It returns ``True`` (failure observed), ``False`` (not observed) or
``None`` (not applicable to this variant, e.g. inter-agent withholding in a
single-agent system, or no gold label available).

Two views are reported for every mode:
* ``occurred``    - the failure appears anywhere in the trace;
* ``user_facing`` - it occurred AND the ticket was resolved autonomously, i.e.
                    the failure reached the requester.
A governance layer cannot stop an upstream agent from failing; what it can do
is stop the failure from reaching the user. The two views separate those.

This annotator is the reproducible, zero-cost labeller. The synopsis' human
double annotation (and the LLM annotator validated against it) is the check on
it; see ``agreement.py`` and ``scripts/mast_labeling_kit.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from ..data.schema import EvalTicket
from ..evaluation.outcomes import (
    answer_correct,
    answer_produced,
    delivered,
    primary_citation,
    step_citations,
)
from .taxonomy import MODE_CODES

ANNOTATOR_VERSION = "mast-rules-v1"

# Canonical node order; a trace that goes backwards has been reset.
_NODE_ORDER = {
    "intake": 0, "single_agent": 0, "retrieval": 1, "resolution": 2, "calibration": 3,
    "governance": 4, "deliver": 5, "escalate": 5,
}
_CLARIFICATION_TYPES = frozenset({"ambiguous", "insufficient", "multi_issue"})
_REQUIRED_TERMINAL_FIELDS = ("ticket_id", "raw_text", "category", "priority", "outcome", "final_response")
_WS = re.compile(r"\s+")

GOVERNED = frozenset({"naive_governed", "calibration_governed", "multi_agent_raw", "multi_agent_calibrated"})
MULTI_AGENT = frozenset({"ungoverned"}) | GOVERNED


@dataclass
class TraceContext:
    variant: str
    final: dict[str, Any]
    ticket: EvalTicket | None = None
    min_relevance: float = 0.25
    naive_threshold: float = 0.70
    max_steps: int = 8

    @property
    def path(self) -> list[str]:
        return [str(e.get("agent")) for e in self.final.get("agent_trace") or []]

    @property
    def is_multi_agent(self) -> bool:
        return self.variant in MULTI_AGENT


def _norm_step(step: str) -> str:
    return _WS.sub(" ", re.sub(r"\[[^\]]*\]", "", str(step))).strip().lower()


# --------------------------------------------------------------------------- #
# Detectors
# --------------------------------------------------------------------------- #


def fm_1_1(c: TraceContext) -> bool | None:
    f = c.final
    if not answer_produced(f):
        return False
    scores = [float(d.get("score", 0.0)) for d in f.get("retrieved_docs") or []]
    ungrounded = not scores or max(scores) < c.min_relevance
    uncited_step = any(not step_citations([s]) for s in f.get("resolution_steps") or [])
    too_many = len(f.get("resolution_steps") or []) > c.max_steps
    no_citations = not (f.get("citations") or [])
    return ungrounded or uncited_step or too_many or no_citations


def fm_1_2(c: TraceContext) -> bool | None:
    if not c.is_multi_agent:
        return None  # a single agent has no role boundary to cross
    for event in c.final.get("agent_trace") or []:
        if event.get("agent") == "intake" and {"steps", "solution"} & set(event.get("payload") or {}):
            return True
    return False


def fm_1_3(c: TraceContext) -> bool | None:
    steps = [_norm_step(s) for s in c.final.get("resolution_steps") or []]
    if len(steps) != len(set(steps)):
        return True
    path = [p for p in c.path if p not in ("deliver", "escalate")]
    return len(path) != len(set(path))


def fm_1_4(c: TraceContext) -> bool | None:
    return any(key not in c.final for key in _REQUIRED_TERMINAL_FIELDS)


def fm_1_5(c: TraceContext) -> bool | None:
    return c.final.get("outcome") not in ("resolved", "escalated")


def fm_2_1(c: TraceContext) -> bool | None:
    order = [_NODE_ORDER.get(agent, 99) for agent in c.path]
    return any(later < earlier for earlier, later in zip(order, order[1:]))


def fm_2_2(c: TraceContext) -> bool | None:
    if c.ticket is None:
        return None
    return c.ticket.adversarial_type in _CLARIFICATION_TYPES and delivered(c.final)


def fm_2_3(c: TraceContext) -> bool | None:
    if c.ticket is None:
        return None
    if not answer_produced(c.final):
        return False
    return not answer_correct(c.final, c.ticket)


def fm_2_4(c: TraceContext) -> bool | None:
    if not c.is_multi_agent:
        return None
    code = str((c.final.get("entities") or {}).get("error_code") or "").strip().lower()
    if not code:
        return False
    return code not in str(c.final.get("retrieval_query") or "").lower()


def fm_2_5(c: TraceContext) -> bool | None:
    f = c.final
    retrieved = {str(d.get("doc_id")) for d in f.get("retrieved_docs") or []}
    for event in f.get("agent_trace") or []:
        if (event.get("payload") or {}).get("hallucinated_citations"):
            return True
    if any(doc not in retrieved for doc in (f.get("citations") or [])):
        return True
    top = max((float(d.get("score", 0.0)) for d in f.get("retrieved_docs") or []), default=0.0)
    return answer_produced(f) and float(f.get("confidence_score") or 0.0) >= c.naive_threshold and top < c.min_relevance


def fm_2_6(c: TraceContext) -> bool | None:
    f = c.final
    produced = answer_produced(f)
    if produced and set(step_citations(f.get("resolution_steps"))) != set(f.get("citations") or []):
        return True
    if not produced and float(f.get("confidence_score") or 0.0) > 0.0:
        return True
    verdict = f.get("governance_verdict")
    if verdict in ("SAFE_TO_RESOLVE", "ESCALATE_TO_HUMAN", "BLOCKED"):
        return bool(f.get("escalation_flag")) != (verdict != "SAFE_TO_RESOLVE")
    return False


def fm_3_1(c: TraceContext) -> bool | None:
    f = c.final
    if delivered(f) and not answer_produced(f):
        return True
    if c.ticket is not None and c.ticket.gold_doc_id and c.is_multi_agent:
        return "retrieval" not in c.path
    return False


def _flawed_delivery(c: TraceContext) -> bool | None:
    """Delivered although the answer was wrong/empty or policy required a human."""
    if c.ticket is None:
        return None
    return delivered(c.final) and (c.ticket.should_escalate or not answer_correct(c.final, c.ticket))


def fm_3_2(c: TraceContext) -> bool | None:
    # A missing check is a failure when it lets a flawed output through. A
    # correct answer that happened to go out unchecked is not labeled, so the
    # mode measures consequences, not merely the absence of a gate.
    if c.variant in GOVERNED:
        return False
    return _flawed_delivery(c)


def fm_3_3(c: TraceContext) -> bool | None:
    if c.variant not in GOVERNED:
        return None  # no independent verification ran, so none could be wrong
    return _flawed_delivery(c)


DETECTORS: dict[str, Callable[[TraceContext], bool | None]] = {
    "FM-1.1": fm_1_1, "FM-1.2": fm_1_2, "FM-1.3": fm_1_3, "FM-1.4": fm_1_4, "FM-1.5": fm_1_5,
    "FM-2.1": fm_2_1, "FM-2.2": fm_2_2, "FM-2.3": fm_2_3, "FM-2.4": fm_2_4, "FM-2.5": fm_2_5,
    "FM-2.6": fm_2_6, "FM-3.1": fm_3_1, "FM-3.2": fm_3_2, "FM-3.3": fm_3_3,
}
assert tuple(DETECTORS) == MODE_CODES


def annotate(context: TraceContext) -> dict[str, dict[str, bool | None]]:
    """Label one trace with all 14 MAST modes (occurred / user_facing)."""
    is_delivered = delivered(context.final)
    labels: dict[str, dict[str, bool | None]] = {}
    for code, detector in DETECTORS.items():
        occurred = detector(context)
        labels[code] = {
            "occurred": occurred,
            "user_facing": None if occurred is None else bool(occurred and is_delivered),
        }
    return labels


def primary_citation_of(final: dict[str, Any]) -> str | None:
    """Re-exported for the labeling kit."""
    return primary_citation(final)
