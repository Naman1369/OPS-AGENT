"""Trace replay: re-decide recorded runs under a different G3 policy.

The Governance Agent is a pure function of the state, and the naively-governed
(V3) and calibration-governed (V4) pipelines are identical up to check G3. So
the V4 decision for any ticket can be recomputed from the V3 record alone:

    delivered  <=>  every non-G3 check passed  AND  T(raw) >= threshold

This is the synopsis' "replaying of the execution traces" (component E). It
makes threshold sensitivity analysis cheap and exactly reproducible; the
evaluation script checks that replay agrees with really running V4.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..calibration.profile import CalibrationProfile


def replay_record(record: dict[str, Any], profile: CalibrationProfile) -> dict[str, Any]:
    """A V4 record derived from a V3 record under ``profile``."""
    calibrated = profile.transform(record["confidence_raw"])
    passes_g3 = calibrated >= profile.threshold
    is_delivered = bool(record["eligible_except_g3"]) and passes_g3
    needs_human = bool(record["should_escalate"]) or not bool(record["answer_correct"])
    if is_delivered:
        outcome = "unsafe_resolution" if needs_human else "correct_resolution"
    else:
        outcome = "necessary_escalation" if needs_human else "unnecessary_escalation"
    replayed = dict(record)
    replayed.update(
        {
            "variant": "calibration_governed",
            "confidence_calibrated": calibrated,
            "confidence_basis": "calibrated",
            "confidence_gate": calibrated,
            "threshold_applied": profile.threshold,
            "delivered": is_delivered,
            "outcome_class": outcome,
            "replayed": True,
        }
    )
    return replayed


def replay(records: Sequence[dict[str, Any]], profile: CalibrationProfile) -> list[dict[str, Any]]:
    return [replay_record(record, profile) for record in records]
