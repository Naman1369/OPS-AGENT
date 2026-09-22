"""Stratified, seeded train / calibration / test split (synopsis Phase 2: 70:15:15).

Roles of the three splits in this project:

* train       - development only: prompt refinement and the formative
                (iteration-1) failure analysis. Never used to fit anything
                that is later scored.
* calibration - the Resolution Agent's raw confidences recorded here are used
                to fit the temperature (Week 8-9) and to select the escalation
                threshold (Week 10-12).
* test        - touched only by the final comparative evaluation (Week 13-14).

Stratification keeps every stratum (each in-KB category and each adversarial
ticket type) represented in every split, so a small calibration split cannot
end up with, say, no security tickets at all.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from .schema import EvalTicket

DEFAULT_RATIOS = (0.70, 0.15, 0.15)
SPLIT_NAMES = ("train", "calibration", "test")


@dataclass
class DatasetSplit:
    seed: int
    train: list[EvalTicket]
    calibration: list[EvalTicket]
    test: list[EvalTicket]

    def as_ids(self) -> dict[str, list[str]]:
        return {
            "train": [t.ticket_id for t in self.train],
            "calibration": [t.ticket_id for t in self.calibration],
            "test": [t.ticket_id for t in self.test],
        }

    def sizes(self) -> dict[str, int]:
        return {name: len(getattr(self, name)) for name in SPLIT_NAMES}


def _allocate(count: int, ratios: Sequence[float], rng: random.Random) -> list[int]:
    """Largest-remainder allocation of ``count`` items to the three splits.

    Ties between equal remainders are broken by the seeded RNG so that no split
    is systematically favoured when many small strata round the same way.
    """
    raw = [count * r for r in ratios]
    base = [math.floor(value) for value in raw]
    remainder = count - sum(base)
    tie_break = [rng.random() for _ in ratios]
    order = sorted(
        range(len(ratios)),
        key=lambda i: (round(raw[i] - base[i], 9), tie_break[i]),
        reverse=True,
    )
    for index in order[:remainder]:
        base[index] += 1
    return base


def stratified_split(
    tickets: Sequence[EvalTicket],
    seed: int = 42,
    ratios: Sequence[float] = DEFAULT_RATIOS,
) -> DatasetSplit:
    """Split per stratum with a seeded shuffle; deterministic for a given seed."""
    if len(ratios) != 3 or abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError("ratios must be three numbers summing to 1.0")

    by_stratum: dict[str, list[EvalTicket]] = defaultdict(list)
    for ticket in sorted(tickets, key=lambda t: t.ticket_id):
        by_stratum[ticket.stratum].append(ticket)

    rng = random.Random(seed)
    parts: dict[str, list[EvalTicket]] = {name: [] for name in SPLIT_NAMES}
    for stratum in sorted(by_stratum):
        members = list(by_stratum[stratum])
        rng.shuffle(members)
        n_train, n_cal, _ = _allocate(len(members), ratios, rng)
        parts["train"].extend(members[:n_train])
        parts["calibration"].extend(members[n_train:n_train + n_cal])
        parts["test"].extend(members[n_train + n_cal:])

    for name in SPLIT_NAMES:
        parts[name].sort(key=lambda t: t.ticket_id)
    return DatasetSplit(seed=seed, **parts)
