"""Evaluation data: schema, cleaning, stratified splits and public-dataset adapters."""

from __future__ import annotations

import json
from pathlib import Path

from .preprocessing import PreprocessReport, normalise_text, preprocess, token_jaccard
from .schema import (
    ADVERSARIAL_TYPES,
    GROUND_TRUTH_POLICY_VERSION,
    EvalTicket,
    policy_should_escalate,
)
from .splits import DEFAULT_RATIOS, DatasetSplit, stratified_split

DEFAULT_DATASET_PATH = Path(__file__).resolve().parents[3] / "data" / "eval" / "dataset.jsonl"


def load_dataset(path: Path | str | None = None) -> list[EvalTicket]:
    """Load the processed evaluation set written by ``scripts/build_dataset.py``."""
    dataset_path = Path(path) if path else DEFAULT_DATASET_PATH
    if not dataset_path.exists():
        raise FileNotFoundError(
            f"{dataset_path} not found. Build it first: python scripts/build_dataset.py"
        )
    tickets = []
    with open(dataset_path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                tickets.append(EvalTicket.from_dict(json.loads(line)))
    return tickets


__all__ = [
    "ADVERSARIAL_TYPES",
    "DEFAULT_DATASET_PATH",
    "DEFAULT_RATIOS",
    "DatasetSplit",
    "EvalTicket",
    "GROUND_TRUTH_POLICY_VERSION",
    "PreprocessReport",
    "load_dataset",
    "normalise_text",
    "policy_should_escalate",
    "preprocess",
    "stratified_split",
    "token_jaccard",
]
