"""Confidence calibration (Weeks 8-9) and risk-controlled thresholds (Weeks 10-12)."""

from .metrics import (
    aurc,
    auroc,
    brier_score,
    calibration_summary,
    expected_calibration_error,
    maximum_calibration_error,
    negative_log_likelihood,
    reliability_bins,
    risk_coverage_curve,
)
from .profile import (
    CalibrationProfile,
    kb_fingerprint,
    load_profile,
    load_profiles,
    pipeline_fingerprint,
    select_profile,
)
from .risk_control import (
    UNCERTIFIABLE_THRESHOLD,
    ThresholdSelection,
    binomial_pvalue,
    clopper_pearson_upper,
    select_threshold,
)
from .temperature import TemperatureScaler, logit, sigmoid

__all__ = [
    "CalibrationProfile",
    "TemperatureScaler",
    "ThresholdSelection",
    "UNCERTIFIABLE_THRESHOLD",
    "aurc",
    "auroc",
    "binomial_pvalue",
    "brier_score",
    "calibration_summary",
    "clopper_pearson_upper",
    "expected_calibration_error",
    "kb_fingerprint",
    "load_profile",
    "load_profiles",
    "logit",
    "maximum_calibration_error",
    "negative_log_likelihood",
    "pipeline_fingerprint",
    "reliability_bins",
    "risk_coverage_curve",
    "select_profile",
    "select_threshold",
    "sigmoid",
]
