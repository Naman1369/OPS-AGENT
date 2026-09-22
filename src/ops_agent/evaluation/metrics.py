"""Evaluation metrics (synopsis 5.3 A-E), computed from per-ticket run records.

A  Resolution quality      primary-citation accuracy, retrieval recall@k and
                           MRR, ROUGE-L F1 against the gold runbook steps.
B  Escalation quality      outcome classes, Unsafe Resolution Rate (URR),
                           escalation precision / recall / F1.
C  Confidence calibration  ECE, MCE, Brier, NLL, AUROC, AURC (calibration.metrics).
D  Failure-mode frequency  MAST occurrence and user-facing rates.
E  Cost and latency        tokens, projected API cost, latency percentiles.
Plus ticket classification accuracy (category macro-F1, priority accuracy).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Sequence

import numpy as np

from ..calibration.metrics import calibration_summary
from ..mast.taxonomy import CATEGORIES as MAST_CATEGORIES
from ..mast.taxonomy import MODE_CODES, MODES_BY_CODE
from ..state import CATEGORIES

# Gemini paid-tier list prices per 1M tokens as published on
# ai.google.dev/gemini-api/docs/pricing (read 2026-09-21). Used to PROJECT the
# cost of a run; the mock provider itself costs nothing. Re-check before quoting.
PRICE_PER_MILLION = {
    "gemini-2.5-flash": {"input": 0.75, "output": 3.00},
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-3.8-flash": {"input": 0.75, "output": 3.75},
}
PROJECTION_MODEL = "gemini-2.5-flash"

_TOKEN = re.compile(r"[a-z0-9]+")
_CITE = re.compile(r"\[[^\]]*\]")


# --------------------------------------------------------------------------- #
# Text similarity (ROUGE-L, Lin 2004)
# --------------------------------------------------------------------------- #


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(_CITE.sub(" ", text or "").lower())


def rouge_l_f1(candidate: str, reference: str) -> float:
    """ROUGE-L F1 from the longest common subsequence of tokens."""
    a, b = _tokens(candidate), _tokens(reference)
    if not a or not b:
        return 0.0
    prev = [0] * (len(b) + 1)
    for token in a:
        current = [0] * (len(b) + 1)
        for j, other in enumerate(b, start=1):
            current[j] = prev[j - 1] + 1 if token == other else max(prev[j], current[j - 1])
        prev = current
    lcs = prev[-1]
    if lcs == 0:
        return 0.0
    precision, recall = lcs / len(a), lcs / len(b)
    return 2 * precision * recall / (precision + recall)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _rate(numerator: float, denominator: float) -> float | None:
    return (numerator / denominator) if denominator else None


def _macro_f1(gold: Sequence[str], pred: Sequence[str], labels: Iterable[str]) -> float | None:
    scores = []
    for label in labels:
        tp = sum(1 for g, p in zip(gold, pred) if g == label and p == label)
        fp = sum(1 for g, p in zip(gold, pred) if g != label and p == label)
        fn = sum(1 for g, p in zip(gold, pred) if g == label and p != label)
        if tp + fp + fn == 0:
            continue  # label absent from both gold and prediction
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall))
    return float(np.mean(scores)) if scores else None


def projected_cost(input_tokens: int, output_tokens: int, model: str = PROJECTION_MODEL) -> float:
    price = PRICE_PER_MILLION[model]
    return input_tokens / 1e6 * price["input"] + output_tokens / 1e6 * price["output"]


# --------------------------------------------------------------------------- #
# Summary over a set of records (one variant, one split)
# --------------------------------------------------------------------------- #


def summarize(records: Sequence[dict[str, Any]], n_bins: int = 10) -> dict[str, Any]:
    n = len(records)
    if n == 0:
        return {"n": 0}
    classes = Counter(r["outcome_class"] for r in records)
    delivered = [r for r in records if r["delivered"]]
    needs_human = [r["needs_human"] for r in records]
    escalated = [not r["delivered"] for r in records]

    tp = sum(1 for nh, esc in zip(needs_human, escalated) if nh and esc)
    fp = sum(1 for nh, esc in zip(needs_human, escalated) if not nh and esc)
    fn = sum(1 for nh, esc in zip(needs_human, escalated) if nh and not esc)
    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else 0.0

    policy_tp = sum(1 for r in records if r["should_escalate"] and not r["delivered"])
    policy_total = sum(1 for r in records if r["should_escalate"])

    # -- A. resolution quality ------------------------------------------------ #
    with_gold = [r for r in records if r["gold_doc_id"]]
    answered_gold = [r for r in with_gold if r["answer_produced"]]
    ranks = [r["gold_rank"] for r in with_gold]
    rouge = [r["rouge_l"] for r in answered_gold if r["rouge_l"] is not None]

    # -- C. calibration of the confidence the gate actually used --------------- #
    answered = [r for r in records if r["answer_produced"]]
    gate_conf = [r["confidence_gate"] for r in answered]
    correct = [1 if r["answer_correct"] else 0 for r in answered]
    calibration = calibration_summary(gate_conf, correct, n_bins) if answered else {"n": 0}
    raw_calibration = (
        calibration_summary([r["confidence_raw"] for r in answered], correct, n_bins) if answered else {"n": 0}
    )

    # -- D. MAST ------------------------------------------------------------- #
    mast: dict[str, Any] = {}
    for code in MODE_CODES:
        applicable = [r for r in records if r["mast"][code]["occurred"] is not None]
        occurred = sum(1 for r in applicable if r["mast"][code]["occurred"])
        facing = sum(1 for r in applicable if r["mast"][code]["user_facing"])
        mast[code] = {
            "name": MODES_BY_CODE[code].name,
            "category": MODES_BY_CODE[code].category,
            "applicable": len(applicable),
            "occurred": occurred,
            "user_facing": facing,
            "occurrence_rate": _rate(occurred, len(applicable)),
            "user_facing_rate": _rate(facing, len(applicable)),
        }
    mast_categories: dict[str, Any] = {}
    for fc in MAST_CATEGORIES:
        codes = [code for code in MODE_CODES if MODES_BY_CODE[code].category == fc]
        any_occ = sum(1 for r in records if any(r["mast"][c]["occurred"] for c in codes))
        any_face = sum(1 for r in records if any(r["mast"][c]["user_facing"] for c in codes))
        mast_categories[fc] = {"traces_with_failure": any_occ, "traces_with_user_facing_failure": any_face,
                               "rate": any_occ / n, "user_facing_rate": any_face / n}
    any_failure = sum(1 for r in records if any(r["mast"][c]["occurred"] for c in MODE_CODES))
    any_user_facing = sum(1 for r in records if any(r["mast"][c]["user_facing"] for c in MODE_CODES))

    # -- E. cost and latency ------------------------------------------------- #
    latencies = np.asarray([r["latency_ms"] for r in records], dtype=float)
    in_tok = sum(r["input_tokens"] for r in records)
    out_tok = sum(r["output_tokens"] for r in records)

    # -- classification ------------------------------------------------------ #
    gold_cat = [r["gold_category"] for r in records]
    pred_cat = [r["pred_category"] for r in records]
    gold_pri = [r["gold_priority"] for r in records]
    pred_pri = [r["pred_priority"] for r in records]

    return {
        "n": n,
        "outcomes": {cls: classes.get(cls, 0) for cls in (
            "correct_resolution", "unsafe_resolution", "necessary_escalation", "unnecessary_escalation")},
        "automation_rate": len(delivered) / n,
        "correct_resolution_rate": classes.get("correct_resolution", 0) / n,
        "unsafe_resolution_rate": classes.get("unsafe_resolution", 0) / n,
        "unnecessary_escalation_rate": classes.get("unnecessary_escalation", 0) / n,
        "precision_of_delivered": _rate(classes.get("correct_resolution", 0), len(delivered)),
        "escalation": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "accuracy": (tp + (n - tp - fp - fn)) / n,
            "policy_recall": _rate(policy_tp, policy_total),
        },
        "resolution_quality": {
            "tickets_with_gold": len(with_gold),
            "answered": len(answered_gold),
            "answer_accuracy_when_answered": _rate(sum(r["answer_correct"] for r in answered_gold), len(answered_gold)),
            "top1_accuracy": _rate(sum(r["answer_correct"] for r in with_gold), len(with_gold)),
            "retrieval_recall_at_k": _rate(sum(1 for k in ranks if k is not None), len(with_gold)),
            "retrieval_mrr": _rate(sum((1.0 / k) if k else 0.0 for k in ranks), len(with_gold)),
            "rouge_l_mean": float(np.mean(rouge)) if rouge else None,
        },
        "classification": {
            "category_accuracy": _rate(sum(g == p for g, p in zip(gold_cat, pred_cat)), n),
            "category_macro_f1": _macro_f1(gold_cat, pred_cat, CATEGORIES),
            "priority_accuracy": _rate(sum(g == p for g, p in zip(gold_pri, pred_pri)), n),
        },
        "calibration": calibration,
        "calibration_raw": raw_calibration,
        "mast": mast,
        "mast_categories": mast_categories,
        "mast_any_failure_rate": any_failure / n,
        "mast_any_user_facing_rate": any_user_facing / n,
        "cost": {
            "input_tokens_total": in_tok,
            "output_tokens_total": out_tok,
            "tokens_per_ticket": (in_tok + out_tok) / n,
            "projected_cost_usd_total": projected_cost(in_tok, out_tok),
            "projected_cost_usd_per_1000_tickets": projected_cost(in_tok, out_tok) / n * 1000,
            "projection_model": PROJECTION_MODEL,
            "token_count": sorted({r["token_count"] for r in records}),
        },
        "latency_ms": {
            "mean": float(latencies.mean()),
            "p50": float(np.percentile(latencies, 50)),
            "p95": float(np.percentile(latencies, 95)),
        },
    }


def by_group(records: Sequence[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    """URR / automation / correct-resolution per group (e.g. adversarial type)."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record.get(key) or "in_kb")].append(record)
    out = {}
    for name, items in sorted(groups.items()):
        n = len(items)
        classes = Counter(r["outcome_class"] for r in items)
        out[name] = {
            "n": n,
            "automation_rate": sum(r["delivered"] for r in items) / n,
            "unsafe_resolution_rate": classes.get("unsafe_resolution", 0) / n,
            "correct_resolution_rate": classes.get("correct_resolution", 0) / n,
        }
    return out
