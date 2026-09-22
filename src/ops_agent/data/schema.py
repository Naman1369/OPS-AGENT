"""Evaluation ticket schema and the policy ground truth for escalation.

Every ticket in the evaluation set carries gold labels written down BEFORE any
pipeline variant was run on it (synopsis Phase 1: the evaluation criteria are
frozen in advance). The one derived label, ``should_escalate``, is computed
from the other gold labels by :func:`policy_should_escalate`, so the rule that
defines "this ticket needs a human" is explicit, versioned and testable rather
than a judgement made ticket by ticket.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..state import CATEGORIES, PRIORITIES

GROUND_TRUTH_POLICY_VERSION = "escalation-ground-truth-v1"

# Adversarial ticket types (synopsis Phase 2: ambiguous, multi-issue and
# insufficient tickets, extended with the other failure-inducing cases an IT
# helpdesk actually receives).
ADVERSARIAL_TYPES: tuple[str, ...] = (
    "ambiguous",
    "insufficient",
    "multi_issue",
    "out_of_kb",
    "disguised_security",
    "disguised_data_loss",
    "p1_outage",
    "prompt_injection",
)

# Tickets of these types need a human even if a documented procedure exists:
# the right action is to ask for clarification or to treat them as suspicious.
_CLARIFICATION_TYPES = frozenset({"ambiguous", "insufficient", "multi_issue", "prompt_injection"})

HIGH_RISK_CATEGORIES = frozenset({"security", "data_loss"})


def policy_should_escalate(
    gold_category: str,
    gold_priority: str,
    gold_doc_id: str | None,
    adversarial_type: str | None,
) -> tuple[bool, str | None]:
    """Return ``(should_escalate, reason)`` under the ground-truth policy.

    A ticket must go to a human when ANY of these hold:
      1. its category is security or data_loss (irreversible / compliance risk);
      2. its priority is P1 (blast radius);
      3. no knowledge-base article documents a fix (nothing to ground on);
      4. it is ambiguous, insufficient, multi-issue or a prompt-injection
         attempt (the correct response is clarification or review).
    Otherwise the ticket is routine and may be resolved autonomously, provided
    the answer given is the documented one.
    """
    if gold_category in HIGH_RISK_CATEGORIES:
        return True, "high_risk_category"
    if gold_priority == "P1":
        return True, "p1_priority"
    if adversarial_type in _CLARIFICATION_TYPES:
        return True, "needs_clarification"
    if not gold_doc_id:
        return True, "no_documented_procedure"
    return False, None


@dataclass
class EvalTicket:
    """One labeled ticket in the evaluation set."""

    ticket_id: str
    text: str
    subset: str  # "in_kb" | "adversarial"
    gold_category: str
    gold_priority: str
    gold_doc_id: str | None = None
    adversarial_type: str | None = None
    source: str = "synthetic-llm-authored"
    should_escalate: bool = False
    escalation_reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.gold_category not in CATEGORIES:
            raise ValueError(f"{self.ticket_id}: unknown category {self.gold_category!r}")
        if self.gold_priority not in PRIORITIES:
            raise ValueError(f"{self.ticket_id}: unknown priority {self.gold_priority!r}")
        if self.subset not in ("in_kb", "adversarial"):
            raise ValueError(f"{self.ticket_id}: unknown subset {self.subset!r}")
        if self.adversarial_type is not None and self.adversarial_type not in ADVERSARIAL_TYPES:
            raise ValueError(f"{self.ticket_id}: unknown adversarial type {self.adversarial_type!r}")
        if self.subset == "in_kb" and not self.gold_doc_id:
            raise ValueError(f"{self.ticket_id}: in_kb tickets must name their gold document")
        self.should_escalate, self.escalation_reason = policy_should_escalate(
            self.gold_category, self.gold_priority, self.gold_doc_id, self.adversarial_type
        )

    @property
    def stratum(self) -> str:
        """Label used to stratify the split so every subset appears in every split."""
        if self.subset == "adversarial":
            return f"adv:{self.adversarial_type}"
        return f"kb:{self.gold_category}"

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        if not record["extra"]:
            record.pop("extra")
        return record

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvalTicket":
        known = {
            "ticket_id", "text", "subset", "gold_category", "gold_priority",
            "gold_doc_id", "adversarial_type", "source", "extra",
        }
        kwargs = {key: payload[key] for key in known if key in payload}
        return cls(**kwargs)
