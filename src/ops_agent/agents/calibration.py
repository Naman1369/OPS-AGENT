"""Calibration node -- inserted between Resolution and Governance (Week 8-9).

It is not a fifth reasoning agent: it has no prompt and calls no model. It maps
the Resolution Agent's raw confidence through the fitted temperature and
records both values. Neither neighbouring agent's interface changes: the
Resolution Agent still emits ``confidence_score`` (raw, never overwritten) and
the Governance Agent still decides with seven checks, of which only G3 reads
the calibrated value.
"""

from __future__ import annotations

import time
from typing import Any

from ..calibration.profile import CalibrationProfile
from ..state import OpsAgentState, trace_event

AGENT_NAME = "calibration"


def calibration_node(
    state: OpsAgentState, profile: CalibrationProfile | None = None
) -> dict[str, Any]:
    """LangGraph node: attach a calibrated confidence to the draft."""
    started = time.perf_counter()
    raw = float(state.get("confidence_score") or 0.0)

    if profile is None:
        # Pass-through keeps the node usable in a raw pipeline without lying
        # about calibration: the flag stays False.
        return {
            "current_agent": AGENT_NAME,
            "calibrated_confidence": raw,
            "confidence_is_calibrated": False,
            "agent_trace": [
                trace_event(
                    AGENT_NAME,
                    "passthrough",
                    {"confidence_score": raw, "confidence_is_calibrated": False},
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                )
            ],
        }

    calibrated = round(profile.transform(raw), 6)
    return {
        "current_agent": AGENT_NAME,
        "calibrated_confidence": calibrated,
        "confidence_is_calibrated": True,
        "calibration_profile_id": profile.profile_id,
        "agent_trace": [
            trace_event(
                AGENT_NAME,
                "calibrated",
                {
                    "confidence_score": raw,
                    "calibrated_confidence": calibrated,
                    "confidence_is_calibrated": True,
                    "method": profile.method,
                    "temperature": profile.temperature,
                    "calibration_profile_id": profile.profile_id,
                },
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
        ],
    }
