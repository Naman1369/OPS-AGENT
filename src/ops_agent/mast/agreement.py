"""Inter-annotator agreement for MAST labels (Cohen, 1960).

Used three ways in synopsis Phase 6:
  human A vs human B        - is the labeling protocol reliable?
  LLM annotator vs humans   - may the LLM label the remaining traces?
  rule annotator vs humans  - does the deterministic operationalisation match
                              what careful people see?
Interpretation bands follow Landis & Koch (1977).
"""

from __future__ import annotations

from typing import Any, Sequence


def cohen_kappa(first: Sequence[bool | int], second: Sequence[bool | int]) -> float | None:
    """Cohen's kappa for two binary label sequences; ``None`` if undefined."""
    if len(first) != len(second):
        raise ValueError("label sequences must have equal length")
    n = len(first)
    if n == 0:
        return None
    a = [int(bool(x)) for x in first]
    b = [int(bool(x)) for x in second]
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    pa, pb = sum(a) / n, sum(b) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    if expected >= 1.0:
        return None  # both annotators constant and identical: kappa undefined
    return (observed - expected) / (1.0 - expected)


def interpret_kappa(kappa: float | None) -> str:
    if kappa is None:
        return "undefined (no variation)"
    if kappa < 0.0:
        return "poor"
    if kappa <= 0.20:
        return "slight"
    if kappa <= 0.40:
        return "fair"
    if kappa <= 0.60:
        return "moderate"
    if kappa <= 0.80:
        return "substantial"
    return "almost perfect"


def agreement_report(
    labels_a: Sequence[dict[str, bool]],
    labels_b: Sequence[dict[str, bool]],
    codes: Sequence[str],
) -> dict[str, Any]:
    """Per-mode and pooled agreement between two annotators over the same traces."""
    if len(labels_a) != len(labels_b):
        raise ValueError("both annotators must label the same traces")
    per_mode: dict[str, Any] = {}
    pooled_a: list[int] = []
    pooled_b: list[int] = []
    for code in codes:
        a = [int(bool(row.get(code))) for row in labels_a]
        b = [int(bool(row.get(code))) for row in labels_b]
        pooled_a += a
        pooled_b += b
        kappa = cohen_kappa(a, b)
        per_mode[code] = {
            "kappa": kappa,
            "interpretation": interpret_kappa(kappa),
            "percent_agreement": (sum(x == y for x, y in zip(a, b)) / len(a)) if a else None,
            "positives_a": sum(a),
            "positives_b": sum(b),
        }
    pooled = cohen_kappa(pooled_a, pooled_b)
    return {
        "n_traces": len(labels_a),
        "pooled_kappa": pooled,
        "pooled_interpretation": interpret_kappa(pooled),
        "per_mode": per_mode,
    }
