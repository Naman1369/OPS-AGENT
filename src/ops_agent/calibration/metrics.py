"""Calibration and selective-prediction metrics (synopsis 5.3 C).

All functions take ``confidence`` (predicted probability that the answer is
correct, in [0, 1]) and ``correct`` (1 if the answer was in fact correct).

* ECE - Expected Calibration Error (Naeini et al., 2015; Guo et al., 2017):
  the bin-weighted mean gap between accuracy and confidence.
* MCE - Maximum Calibration Error: the worst bin's gap.
* Brier score (Brier, 1950) and negative log-likelihood: proper scoring rules.
* AUROC - how well confidence *ranks* correct above incorrect answers. A
  monotone recalibration such as temperature scaling cannot change it, which is
  why it is reported alongside ECE.
* Risk-coverage curve and AURC (Geifman & El-Yaniv, 2017): the error rate among
  the answers kept when only the most confident fraction is auto-resolved.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

_EPS = 1e-6


def _arrays(confidence: Sequence[float], correct: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    conf = np.asarray(confidence, dtype=float).reshape(-1)
    y = np.asarray(correct, dtype=float).reshape(-1)
    if conf.shape != y.shape:
        raise ValueError("confidence and correct must have the same length")
    if conf.size and (np.nanmin(conf) < 0.0 or np.nanmax(conf) > 1.0):
        raise ValueError("confidence values must lie in [0, 1]")
    if y.size and not np.all(np.isin(y, (0.0, 1.0))):
        raise ValueError("correct must be binary (0/1)")
    return conf, y


def reliability_bins(
    confidence: Sequence[float],
    correct: Sequence[float],
    n_bins: int = 10,
    strategy: str = "uniform",
) -> list[dict[str, Any]]:
    """Per-bin count, mean confidence and accuracy (the reliability diagram data).

    ``strategy="uniform"`` uses equal-width bins on [0, 1] (the standard ECE);
    ``"quantile"`` uses equal-mass bins, which are more stable on small samples.
    """
    conf, y = _arrays(confidence, correct)
    if strategy == "uniform":
        edges = np.linspace(0.0, 1.0, n_bins + 1)
    elif strategy == "quantile":
        edges = np.unique(np.quantile(conf, np.linspace(0.0, 1.0, n_bins + 1))) if conf.size else np.array([0.0, 1.0])
        edges[0], edges[-1] = 0.0, 1.0
    else:
        raise ValueError(f"unknown binning strategy {strategy!r}")

    bins: list[dict[str, Any]] = []
    last = len(edges) - 2
    for index in range(len(edges) - 1):
        lower, upper = float(edges[index]), float(edges[index + 1])
        if index == last:
            mask = (conf >= lower) & (conf <= upper)
        else:
            mask = (conf >= lower) & (conf < upper)
        count = int(mask.sum())
        mean_conf = float(conf[mask].mean()) if count else None
        accuracy = float(y[mask].mean()) if count else None
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "count": count,
                "mean_confidence": mean_conf,
                "accuracy": accuracy,
                "gap": (abs(accuracy - mean_conf) if count else None),
            }
        )
    return bins


def expected_calibration_error(
    confidence: Sequence[float], correct: Sequence[float], n_bins: int = 10, strategy: str = "uniform"
) -> float:
    conf, _ = _arrays(confidence, correct)
    if conf.size == 0:
        return float("nan")
    bins = reliability_bins(confidence, correct, n_bins, strategy)
    return float(sum(b["count"] * b["gap"] for b in bins if b["count"]) / conf.size)


def maximum_calibration_error(
    confidence: Sequence[float], correct: Sequence[float], n_bins: int = 10, strategy: str = "uniform"
) -> float:
    bins = [b for b in reliability_bins(confidence, correct, n_bins, strategy) if b["count"]]
    return float(max((b["gap"] for b in bins), default=float("nan")))


def brier_score(confidence: Sequence[float], correct: Sequence[float]) -> float:
    conf, y = _arrays(confidence, correct)
    return float(np.mean((conf - y) ** 2)) if conf.size else float("nan")


def negative_log_likelihood(confidence: Sequence[float], correct: Sequence[float]) -> float:
    conf, y = _arrays(confidence, correct)
    if conf.size == 0:
        return float("nan")
    p = np.clip(conf, _EPS, 1.0 - _EPS)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def auroc(confidence: Sequence[float], correct: Sequence[float]) -> float | None:
    """Area under the ROC curve via the Mann-Whitney U statistic (ties averaged)."""
    conf, y = _arrays(confidence, correct)
    positives, negatives = int(y.sum()), int((1 - y).sum())
    if positives == 0 or negatives == 0:
        return None
    from scipy.stats import rankdata

    ranks = rankdata(conf)
    u = ranks[y == 1].sum() - positives * (positives + 1) / 2.0
    return float(u / (positives * negatives))


def risk_coverage_curve(confidence: Sequence[float], correct: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    """Coverage and selective risk when auto-resolving the top-k most confident."""
    conf, y = _arrays(confidence, correct)
    if conf.size == 0:
        return np.array([]), np.array([])
    order = np.argsort(-conf, kind="mergesort")
    errors = np.cumsum(1.0 - y[order])
    kept = np.arange(1, conf.size + 1)
    return kept / conf.size, errors / kept


def aurc(confidence: Sequence[float], correct: Sequence[float]) -> float:
    """Area under the risk-coverage curve (lower is better)."""
    _, risk = risk_coverage_curve(confidence, correct)
    return float(risk.mean()) if risk.size else float("nan")


def calibration_summary(
    confidence: Sequence[float], correct: Sequence[float], n_bins: int = 10
) -> dict[str, Any]:
    """Every calibration metric in one dictionary (used by reports and profiles)."""
    conf, y = _arrays(confidence, correct)
    return {
        "n": int(conf.size),
        "accuracy": float(y.mean()) if conf.size else float("nan"),
        "mean_confidence": float(conf.mean()) if conf.size else float("nan"),
        "ece": expected_calibration_error(conf, y, n_bins, "uniform"),
        "ece_quantile": expected_calibration_error(conf, y, n_bins, "quantile") if conf.size else float("nan"),
        "mce": maximum_calibration_error(conf, y, n_bins, "uniform"),
        "brier": brier_score(conf, y),
        "nll": negative_log_likelihood(conf, y),
        "auroc": auroc(conf, y),
        "aurc": aurc(conf, y),
    }
