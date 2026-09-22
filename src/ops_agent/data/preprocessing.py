"""Cleaning, normalisation and de-duplication (synopsis Phase 2).

The steps are deliberately simple and fully deterministic so the processed
dataset is byte-identical on every machine:

1. normalise   - Unicode NFKC, strip control characters, collapse whitespace;
2. validate    - drop empty tickets and tickets with invalid labels;
3. de-duplicate - exact duplicates on the normalised, case-folded text, then
                  near-duplicates whose token-set Jaccard similarity is at or
                  above a threshold (first occurrence wins).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

from .schema import EvalTicket

_CONTROL_RE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]")
_WS_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalise_text(text: str) -> str:
    """Canonical form of a ticket body: NFKC, no control chars, single spaces."""
    text = unicodedata.normalize("NFKC", text or "")
    text = _CONTROL_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _dedup_key(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.casefold()))


def token_jaccard(first: str, second: str) -> float:
    a = set(_TOKEN_RE.findall(first.casefold()))
    b = set(_TOKEN_RE.findall(second.casefold()))
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


@dataclass
class PreprocessReport:
    """What the cleaning pass did, for the dataset card."""

    input_rows: int = 0
    kept: int = 0
    dropped_invalid: list[dict[str, Any]] = field(default_factory=list)
    dropped_exact_duplicates: list[str] = field(default_factory=list)
    dropped_near_duplicates: list[tuple[str, str, float]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_rows": self.input_rows,
            "kept": self.kept,
            "dropped_invalid": self.dropped_invalid,
            "dropped_exact_duplicates": self.dropped_exact_duplicates,
            "dropped_near_duplicates": [
                {"dropped": dropped, "kept": kept, "jaccard": round(score, 3)}
                for dropped, kept, score in self.dropped_near_duplicates
            ],
        }


def preprocess(
    rows: Iterable[dict[str, Any]],
    near_duplicate_threshold: float = 0.9,
) -> tuple[list[EvalTicket], PreprocessReport]:
    """Normalise, validate and de-duplicate raw ticket rows."""
    report = PreprocessReport()
    kept: list[EvalTicket] = []
    seen_keys: dict[str, str] = {}

    for row in rows:
        report.input_rows += 1
        payload = dict(row)
        payload["text"] = normalise_text(str(payload.get("text", "")))
        if not payload["text"]:
            report.dropped_invalid.append({"ticket_id": payload.get("ticket_id"), "reason": "empty text"})
            continue
        try:
            ticket = EvalTicket.from_dict(payload)
        except (TypeError, ValueError, KeyError) as exc:
            report.dropped_invalid.append({"ticket_id": payload.get("ticket_id"), "reason": str(exc)})
            continue

        key = _dedup_key(ticket.text)
        if key in seen_keys:
            report.dropped_exact_duplicates.append(ticket.ticket_id)
            continue

        near = next(
            (
                (other.ticket_id, score)
                for other in kept
                if (score := token_jaccard(ticket.text, other.text)) >= near_duplicate_threshold
            ),
            None,
        )
        if near is not None:
            report.dropped_near_duplicates.append((ticket.ticket_id, near[0], near[1]))
            continue

        seen_keys[key] = ticket.ticket_id
        kept.append(ticket)

    report.kept = len(kept)
    return kept, report
