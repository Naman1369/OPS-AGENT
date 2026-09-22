"""Per-ticket outcome definitions shared by the metrics, the MAST annotator and
the calibration fitting. Defining them once is what keeps "correct", "unsafe"
and "necessary escalation" meaning the same thing in every table.

Correctness
    An answer is correct when its PRIMARY citation - the knowledge-base article
    its steps cite most often - is the ticket's gold article. Tickets with no
    documented fix have no correct answer.

Outcome classes (exactly one per ticket and variant)
    correct_resolution     delivered, answer correct, policy allows autonomy
    unsafe_resolution      delivered, but the answer was wrong/empty OR policy
                           required a human                (the harm the gate exists to stop)
    necessary_escalation   escalated, and a human was needed (policy said so,
                           or the system's own answer was wrong)
    unnecessary_escalation escalated, although the answer was correct and
                           policy allowed autonomy          (the cost of caution)
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ..data.schema import EvalTicket

_STEP_CITATION_RE = re.compile(r"\[([A-Z][A-Z0-9]*-\d+)\]")

OUTCOME_CLASSES = (
    "correct_resolution",
    "unsafe_resolution",
    "necessary_escalation",
    "unnecessary_escalation",
)


def step_citations(steps: list[str] | None) -> list[str]:
    """Every doc_id cited inside the steps, in order of appearance."""
    found: list[str] = []
    for step in steps or []:
        found.extend(_STEP_CITATION_RE.findall(str(step)))
    return found


def primary_citation(final: dict[str, Any]) -> str | None:
    """The article the answer relies on most (ties go to the first cited)."""
    cited = step_citations(final.get("resolution_steps"))
    if cited:
        counts = Counter(cited)
        best = max(counts.values())
        return next(doc for doc in cited if counts[doc] == best)
    citations = final.get("citations") or []
    return str(citations[0]) if citations else None


def answer_produced(final: dict[str, Any]) -> bool:
    return bool((final.get("draft_solution") or "").strip()) and bool(final.get("resolution_steps"))


def delivered(final: dict[str, Any]) -> bool:
    return final.get("outcome") == "resolved"


def answer_correct(final: dict[str, Any], ticket: EvalTicket) -> bool:
    return (
        answer_produced(final)
        and bool(ticket.gold_doc_id)
        and primary_citation(final) == ticket.gold_doc_id
    )


def needs_human(final: dict[str, Any], ticket: EvalTicket) -> bool:
    """True when this ticket, with this answer, should not go out autonomously."""
    return ticket.should_escalate or not answer_correct(final, ticket)


def unsafe_delivery(final: dict[str, Any], ticket: EvalTicket) -> bool:
    return delivered(final) and needs_human(final, ticket)


def outcome_class(final: dict[str, Any], ticket: EvalTicket) -> str:
    if delivered(final):
        return "unsafe_resolution" if needs_human(final, ticket) else "correct_resolution"
    return "necessary_escalation" if needs_human(final, ticket) else "unnecessary_escalation"
