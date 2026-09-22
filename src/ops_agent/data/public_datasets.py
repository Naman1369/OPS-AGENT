"""Adapters for the two public Kaggle datasets named in the synopsis.

* Goh, "IT Service Ticket Classification Dataset" (Kaggle:
  adisongoh/it-service-ticket-classification-dataset) - short ticket texts with
  a ``Topic_group`` label.
* Bueck, "Customer IT Support - Ticket Dataset" (Kaggle:
  tobiasbueck/multilingual-customer-support-tickets) - synthetic e-mail tickets
  with subject, body, agent answer, queue, priority and language.

Neither dataset ships with this repository (licence and size), and neither is
labeled against this project's knowledge base, so they cannot supply a gold
document or a correctness label. They are used for what their labels can
support: Intake category / priority agreement and out-of-distribution pipeline
behaviour. Column detection is tolerant because the published CSVs have been
revised several times.

Download (requires a Kaggle API token):
    kaggle datasets download -d adisongoh/it-service-ticket-classification-dataset -p data/raw --unzip
    kaggle datasets download -d tobiasbueck/multilingual-customer-support-tickets -p data/raw --unzip
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .preprocessing import normalise_text

# Goh Topic_group -> this project's category vocabulary. Topics with no
# counterpart map to "other" rather than being forced into a wrong category.
GOH_CATEGORY_MAP: dict[str, str] = {
    "hardware": "hardware",
    "access": "access",
    "administrative rights": "access",
    "storage": "hardware",
    "hr support": "other",
    "purchase": "other",
    "internal project": "other",
    "miscellaneous": "other",
}

# Bueck priority -> P1..P4. "critical" appears in later dataset versions.
BUECK_PRIORITY_MAP: dict[str, str] = {
    "critical": "P1",
    "high": "P2",
    "medium": "P3",
    "low": "P4",
    "very_low": "P4",
}

_TEXT_COLUMNS = ("document", "text", "body", "description", "ticket")
_GOH_LABEL_COLUMNS = ("topic_group", "topic", "label", "category")


@dataclass
class PublicTicket:
    """A normalised ticket from a public dataset (no gold document)."""

    ticket_id: str
    text: str
    source: str
    label_category: str | None = None
    label_priority: str | None = None
    language: str | None = None
    original: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _find_column(header: Iterable[str], candidates: Iterable[str]) -> str | None:
    lowered = {name.strip().lower(): name for name in header}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


def _stable_id(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10].upper()}"


def load_goh(csv_path: Path | str, limit: int | None = None) -> list[PublicTicket]:
    """Load the IT Service Ticket Classification CSV."""
    rows: list[PublicTicket] = []
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        text_col = _find_column(reader.fieldnames or [], _TEXT_COLUMNS)
        label_col = _find_column(reader.fieldnames or [], _GOH_LABEL_COLUMNS)
        if text_col is None or label_col is None:
            raise ValueError(f"Unrecognised columns in {csv_path}: {reader.fieldnames}")
        for record in reader:
            text = normalise_text(record.get(text_col, ""))
            if not text:
                continue
            topic = str(record.get(label_col, "")).strip()
            rows.append(
                PublicTicket(
                    ticket_id=_stable_id("GOH", text),
                    text=text,
                    source="kaggle:adisongoh/it-service-ticket-classification-dataset",
                    label_category=GOH_CATEGORY_MAP.get(topic.lower()),
                    original={"topic_group": topic},
                )
            )
            if limit and len(rows) >= limit:
                break
    return rows


def load_bueck(csv_path: Path | str, language: str = "en", limit: int | None = None) -> list[PublicTicket]:
    """Load the Customer IT Support ticket CSV, keeping one language."""
    rows: list[PublicTicket] = []
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        subject_col = _find_column(header, ("subject", "title"))
        body_col = _find_column(header, ("body", "text", "description"))
        priority_col = _find_column(header, ("priority",))
        language_col = _find_column(header, ("language", "lang"))
        queue_col = _find_column(header, ("queue",))
        type_col = _find_column(header, ("type",))
        if body_col is None:
            raise ValueError(f"Unrecognised columns in {csv_path}: {header}")
        for record in reader:
            lang = str(record.get(language_col, "") or "").strip().lower() if language_col else ""
            if language and lang and lang != language:
                continue
            subject = str(record.get(subject_col, "") or "") if subject_col else ""
            text = normalise_text(f"{subject}. {record.get(body_col, '')}" if subject else record.get(body_col, ""))
            if not text:
                continue
            priority = str(record.get(priority_col, "") or "").strip().lower() if priority_col else ""
            rows.append(
                PublicTicket(
                    ticket_id=_stable_id("BUE", text),
                    text=text,
                    source="kaggle:tobiasbueck/multilingual-customer-support-tickets",
                    label_priority=BUECK_PRIORITY_MAP.get(priority),
                    language=lang or None,
                    original={
                        "priority": priority,
                        "queue": record.get(queue_col) if queue_col else None,
                        "type": record.get(type_col) if type_col else None,
                    },
                )
            )
            if limit and len(rows) >= limit:
                break
    return rows


def deduplicate(tickets: list[PublicTicket]) -> list[PublicTicket]:
    """Drop exact duplicates (same normalised, case-folded text)."""
    seen: set[str] = set()
    unique: list[PublicTicket] = []
    for ticket in tickets:
        key = ticket.text.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(ticket)
    return unique
