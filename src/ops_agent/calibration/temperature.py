"""Temperature scaling for the Resolution Agent's confidence (Week 8-9).

Guo et al. (2017) showed that a single scalar temperature T, fitted on held-out
data by minimising negative log-likelihood, is a strong and simple calibrator.
The Resolution Agent reports one probability ``p`` that its answer is correct,
so the binary form is used:

    z  = logit(p)
    p' = sigmoid(z / T)

T > 1 softens over-confident scores towards 0.5; T < 1 sharpens under-confident
ones. The map is strictly monotone, so the *ranking* of tickets by confidence -
and therefore AUROC - is unchanged: temperature scaling fixes what a score
means, not which tickets score highest. Exactly one parameter is fitted, as the
synopsis specifies (Phase 4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

_EPS = 1e-6
MIN_CALIBRATION_SAMPLES = 10


def logit(p: np.ndarray | float) -> np.ndarray:
    q = np.clip(np.asarray(p, dtype=float), _EPS, 1.0 - _EPS)
    return np.log(q) - np.log1p(-q)


def sigmoid(z: np.ndarray | float) -> np.ndarray:
    z = np.asarray(z, dtype=float)
    return 1.0 / (1.0 + np.exp(-z))


def _nll(log_t: float, z: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(sigmoid(z / math.exp(log_t)), _EPS, 1.0 - _EPS)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


@dataclass
class TemperatureScaler:
    """One-parameter binary temperature scaling."""

    temperature: float = 1.0
    fitted: bool = False
    n_samples: int = 0
    nll_before: float | None = None
    nll_after: float | None = None
    at_bound: bool = False

    def fit(
        self,
        confidence: Sequence[float],
        correct: Sequence[float],
        bounds: tuple[float, float] = (0.05, 20.0),
    ) -> "TemperatureScaler":
        """Fit T by minimising NLL on held-out (calibration-split) pairs."""
        from scipy.optimize import minimize_scalar

        conf = np.asarray(confidence, dtype=float).reshape(-1)
        y = np.asarray(correct, dtype=float).reshape(-1)
        if conf.shape != y.shape:
            raise ValueError("confidence and correct must have the same length")
        if conf.size < MIN_CALIBRATION_SAMPLES:
            raise ValueError(
                f"temperature scaling needs at least {MIN_CALIBRATION_SAMPLES} calibration "
                f"samples, got {conf.size}"
            )
        z = logit(conf)
        result = minimize_scalar(
            _nll,
            bounds=(math.log(bounds[0]), math.log(bounds[1])),
            args=(z, y),
            method="bounded",
            options={"xatol": 1e-6},
        )
        self.temperature = float(math.exp(result.x))
        # A temperature pinned to a search bound means no single T fits: e.g. raw
        # scores sit below 0.5 while most answers are correct - scaling can only
        # push them towards 0.5, never past it. Recorded, not hidden.
        self.at_bound = bool(
            min(abs(result.x - math.log(bounds[0])), abs(result.x - math.log(bounds[1]))) < 1e-3
        )
        self.fitted = True
        self.n_samples = int(conf.size)
        self.nll_before = _nll(0.0, z, y)
        self.nll_after = _nll(float(result.x), z, y)
        return self

    def transform(self, confidence: Sequence[float] | float) -> np.ndarray | float:
        """Map raw confidence to calibrated confidence."""
        scalar = np.isscalar(confidence)
        out = sigmoid(logit(confidence) / self.temperature)
        return float(out) if scalar else out

    def to_dict(self) -> dict:
        return {
            "temperature": self.temperature,
            "fitted": self.fitted,
            "n_samples": self.n_samples,
            "nll_before": self.nll_before,
            "nll_after": self.nll_after,
            "at_bound": self.at_bound,
        }
