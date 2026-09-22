"""Risk-controlled escalation threshold selection (synopsis Phase 5, Weeks 10-12).

The synopsis requires that the escalation threshold is "selected by testing
different values on the calibration set, not chosen arbitrarily". This module
does that with a finite-sample guarantee.

Loss
    For calibration ticket i let s_i be its calibrated confidence, e_i = 1 if
    it clears every governance check except G3 (so G3 alone decides whether it
    is delivered), and u_i = 1 if delivering it would be UNSAFE (the answer is
    wrong, or policy requires a human). At threshold lam the ticket is resolved
    autonomously iff e_i = 1 and s_i >= lam, and the loss is

        L_i(lam) = e_i * u_i * 1[s_i >= lam].

    Its mean R(lam) is the Unsafe Resolution Rate (URR): the fraction of ALL
    tickets that would be resolved autonomously and unsafely. L_i is monotone
    non-increasing in lam - raising the threshold can only remove deliveries.

Primary method - Learn then Test, fixed sequence (Angelopoulos et al., 2025)
    Candidate thresholds form a FIXED grid chosen before seeing any data
    (0.995 down to 0.005 in steps of 0.005). They are tested from the highest
    (safest) downwards; H0(lam): R(lam) > alpha is rejected when the exact
    binomial p-value P(Binomial(N, alpha) <= N * R_hat(lam)) is <= delta.
    Testing stops at the first non-rejection; the lowest rejected lam is used.
    Guarantee: with probability >= 1 - delta over the calibration draw,
    URR(lam_hat) <= alpha, for exchangeable calibration and deployment tickets.

Alternative - Conformal Risk Control (Angelopoulos et al., 2024)
    lam_hat is the lowest grid value such that, for it and every higher value,
    N / (N + 1) * R_hat(lam) + 1 / (N + 1) <= alpha. Guarantee in expectation:
    E[URR(lam_hat)] <= alpha. This is the split-conformal form of the same idea.

If no threshold can be certified the returned threshold is 1.01 (above any
probability): check G3 then fails for every ticket and everything escalates.
Failing closed is the only safe default for a governance gate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np

UNCERTIFIABLE_THRESHOLD = 1.01
DEFAULT_GRID: tuple[float, ...] = tuple(round(0.995 - 0.005 * i, 3) for i in range(199))
METHODS = ("ltt", "crc")


def binomial_pvalue(errors: int, n: int, alpha: float) -> float:
    """Exact p-value for H0: rate > alpha, having seen ``errors`` out of ``n``."""
    from scipy.stats import binom

    if n <= 0:
        return 1.0
    return float(binom.cdf(errors, n, alpha))


def clopper_pearson_upper(errors: int, n: int, delta: float) -> float:
    """One-sided (1 - delta) Clopper-Pearson upper confidence bound on a rate."""
    from scipy.stats import beta

    if n <= 0 or errors >= n:
        return 1.0
    return float(beta.ppf(1.0 - delta, errors + 1, n - errors))


@dataclass
class ThresholdSelection:
    threshold: float
    method: str
    alpha: float
    delta: float
    feasible: bool
    n_calibration: int
    n_eligible: int
    n_auto_resolved: int
    unsafe_auto_resolved: int
    unsafe_resolution_rate: float
    unsafe_rate_upper_bound: float
    conditional_risk: float | None
    coverage: float
    candidates_tested: int

    def to_dict(self) -> dict:
        return asdict(self)


def _as_arrays(scores, unsafe, eligible):
    s = np.asarray(scores, dtype=float).reshape(-1)
    u = np.asarray(unsafe, dtype=int).reshape(-1)
    e = np.ones_like(u) if eligible is None else np.asarray(eligible, dtype=int).reshape(-1)
    if not (s.shape == u.shape == e.shape):
        raise ValueError("scores, unsafe and eligible must have the same length")
    return s, u, e


def select_threshold(
    scores: Sequence[float],
    unsafe: Sequence[int],
    eligible: Sequence[int] | None = None,
    alpha: float = 0.05,
    delta: float = 0.10,
    method: str = "ltt",
    grid: Sequence[float] | None = None,
) -> ThresholdSelection:
    """Lowest grid threshold whose Unsafe Resolution Rate is controlled at ``alpha``."""
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}")
    if not 0.0 < alpha < 1.0 or not 0.0 < delta < 1.0:
        raise ValueError("alpha and delta must lie strictly between 0 and 1")
    s, u, e = _as_arrays(scores, unsafe, eligible)
    n_total = int(s.size)
    if n_total == 0:
        raise ValueError("no calibration data")

    candidates = sorted({float(value) for value in (grid or DEFAULT_GRID)}, reverse=True)
    accepted: float | None = None
    tested = 0
    for lam in candidates:
        losses = int((e * u * (s >= lam)).sum())
        tested += 1
        if method == "ltt":
            ok = binomial_pvalue(losses, n_total, alpha) <= delta
        else:  # crc
            ok = (n_total / (n_total + 1)) * (losses / n_total) + 1.0 / (n_total + 1) <= alpha
        if ok:
            accepted = lam
        else:
            break

    threshold = accepted if accepted is not None else UNCERTIFIABLE_THRESHOLD
    delivered = (e == 1) & (s >= threshold)
    n_delivered = int(delivered.sum())
    unsafe_delivered = int((u[delivered]).sum()) if n_delivered else 0
    return ThresholdSelection(
        threshold=float(threshold),
        method=method,
        alpha=alpha,
        delta=delta,
        feasible=accepted is not None,
        n_calibration=n_total,
        n_eligible=int(e.sum()),
        n_auto_resolved=n_delivered,
        unsafe_auto_resolved=unsafe_delivered,
        unsafe_resolution_rate=unsafe_delivered / n_total,
        unsafe_rate_upper_bound=clopper_pearson_upper(unsafe_delivered, n_total, delta),
        conditional_risk=(unsafe_delivered / n_delivered) if n_delivered else None,
        coverage=n_delivered / n_total,
        candidates_tested=tested,
    )
