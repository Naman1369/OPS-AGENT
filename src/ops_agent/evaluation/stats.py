"""Statistical tests for the comparative evaluation (synopsis Phase 7).

All four variants are run on the SAME tickets, so comparisons are paired:

* McNemar's exact test (McNemar, 1947; recommended for comparing two
  classifiers on one test set by Dietterich, 1998) for a pairwise difference in
  a binary per-ticket outcome such as "resolved unsafely".
* Cochran's Q test (Cochran, 1950) as the omnibus test across all variants.
* Holm's step-down correction (Holm, 1979) for the family of pairwise tests.
* Percentile bootstrap confidence intervals (Efron & Tibshirani, 1993) for
  rates and for paired differences in rates.
* Wilson score intervals for single proportions.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np


def mcnemar_exact(first: Sequence[bool | int], second: Sequence[bool | int]) -> dict[str, float | int]:
    """Two-sided exact McNemar test on paired binary outcomes.

    ``b`` counts tickets where only ``first`` had the outcome, ``c`` where only
    ``second`` did. Under H0 the discordant pairs split 50/50.
    """
    from scipy.stats import binomtest

    a = np.asarray(first, dtype=bool)
    b_ = np.asarray(second, dtype=bool)
    if a.shape != b_.shape:
        raise ValueError("paired outcomes must have equal length")
    b = int(np.sum(a & ~b_))
    c = int(np.sum(~a & b_))
    n = b + c
    p_value = 1.0 if n == 0 else float(binomtest(b, n, 0.5, alternative="two-sided").pvalue)
    return {"only_first": b, "only_second": c, "discordant": n, "p_value": p_value}


def cochran_q(outcomes: np.ndarray) -> dict[str, float | int]:
    """Cochran's Q for an (n_subjects x k_treatments) binary matrix."""
    from scipy.stats import chi2

    x = np.asarray(outcomes, dtype=float)
    if x.ndim != 2 or x.shape[1] < 2:
        raise ValueError("need an n x k matrix with k >= 2")
    k = x.shape[1]
    col = x.sum(axis=0)
    row = x.sum(axis=1)
    total = x.sum()
    denominator = k * total - np.sum(row ** 2)
    if denominator == 0:
        return {"q": 0.0, "df": k - 1, "p_value": 1.0}
    q = (k - 1) * (k * np.sum(col ** 2) - total ** 2) / denominator
    return {"q": float(q), "df": k - 1, "p_value": float(chi2.sf(q, k - 1))}


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values (monotone, capped at 1)."""
    p = np.asarray(p_values, dtype=float)
    m = p.size
    order = np.argsort(p)
    adjusted = np.empty(m)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (m - rank) * p[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[np.ndarray], float] = np.mean,
    n_boot: int = 2000,
    level: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap interval for a statistic of one sample."""
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(n_boot, x.size))
    stats = np.apply_along_axis(statistic, 1, x[idx])
    tail = (1.0 - level) / 2.0
    return (float(np.quantile(stats, tail)), float(np.quantile(stats, 1.0 - tail)))


def paired_bootstrap_diff(
    first: Sequence[float],
    second: Sequence[float],
    n_boot: int = 2000,
    level: float = 0.95,
    seed: int = 0,
) -> dict[str, float]:
    """Mean difference (first - second) over paired tickets, with a bootstrap CI."""
    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    if a.shape != b.shape:
        raise ValueError("paired samples must have equal length")
    diff = a - b
    low, high = bootstrap_ci(diff, np.mean, n_boot, level, seed)
    return {"difference": float(diff.mean()) if diff.size else float("nan"), "ci_low": low, "ci_high": high}


def wilson_interval(successes: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    from scipy.stats import norm

    if n == 0:
        return (float("nan"), float("nan"))
    z = float(norm.ppf(1.0 - (1.0 - level) / 2.0))
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
