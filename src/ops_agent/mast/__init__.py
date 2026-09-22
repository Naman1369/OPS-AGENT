"""MAST failure labeling: taxonomy, rule-based and LLM annotators, agreement."""

from .agreement import agreement_report, cohen_kappa, interpret_kappa
from .rule_annotator import ANNOTATOR_VERSION, DETECTORS, TraceContext, annotate
from .taxonomy import CATEGORIES, FAILURE_MODES, MODE_CODES, MODES_BY_CODE, FailureMode, modes_in_category

__all__ = [
    "ANNOTATOR_VERSION",
    "CATEGORIES",
    "DETECTORS",
    "FAILURE_MODES",
    "FailureMode",
    "MODES_BY_CODE",
    "MODE_CODES",
    "TraceContext",
    "agreement_report",
    "annotate",
    "cohen_kappa",
    "interpret_kappa",
    "modes_in_category",
]
