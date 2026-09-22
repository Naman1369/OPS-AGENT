"""Evaluation harness (synopsis component E, Weeks 13-14).

Runs the four pipeline variants on the same tickets, turns every final state
into a flat run record (outcome class, confidences, MAST labels, cost), and fits
the calibration profile that the calibration-governed variant needs. It works
on traces after the fact and never alters how a ticket is processed.

    V1 single_agent          baseline, raw self-confidence >= 0.70
    V2 ungoverned            four agents, no gate
    V3 naive_governed        four agents + governance, G3 on raw confidence
    V4 calibration_governed  four agents + governance, G3 on calibrated
                             confidence with a risk-controlled threshold
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from ..calibration.metrics import calibration_summary
from ..calibration.profile import CalibrationProfile, pipeline_fingerprint
from ..calibration.risk_control import select_threshold
from ..calibration.temperature import TemperatureScaler
from ..config import SETTINGS
from ..data.schema import EvalTicket
from ..graph import build_graph
from ..knowledge import VectorStore, get_embedder, load_knowledge_base, set_default_store
from ..llm import get_provider
from ..mast.rule_annotator import TraceContext, annotate
from ..state import new_state
from .baselines import SINGLE_AGENT_THRESHOLD, build_single_agent_graph, build_ungoverned_graph
from .metrics import rouge_l_f1
from .outcomes import (
    answer_correct,
    answer_produced,
    delivered,
    needs_human,
    outcome_class,
    primary_citation,
)

VARIANTS = ("single_agent", "ungoverned", "naive_governed", "calibration_governed")
VARIANT_LABELS = {
    "single_agent": "V1 Single agent",
    "ungoverned": "V2 Ungoverned multi-agent",
    "naive_governed": "V3 Naively governed",
    "calibration_governed": "V4 Calibration governed",
}
NON_G3_CHECKS = ("G1_grounded", "G2_cited", "G4_complete", "G5_priority_gate", "G6_category_gate", "G7_intake_clarity")


# --------------------------------------------------------------------------- #
# Environment
# --------------------------------------------------------------------------- #


def build_eval_store(backend: str = "auto") -> VectorStore:
    """A fresh in-memory index of the knowledge base for one evaluation run."""
    settings = SETTINGS.retrieval
    store = VectorStore(
        collection_name=f"ops_agent_eval_{backend}",
        embedder=get_embedder(settings.embedding_model, backend),
        persist_dir=None,
    )
    store.add_documents(load_knowledge_base(settings.kb_dir))
    return store


def gold_resolution_texts(kb_dir: Path | str | None = None) -> dict[str, str]:
    """doc_id -> the article's numbered Resolution steps (the human-written answer)."""
    texts: dict[str, str] = {}
    for doc in load_knowledge_base(kb_dir or SETTINGS.retrieval.kb_dir):
        match = re.search(r"## Resolution\s*(.*?)(?:\n## |\Z)", doc.body, re.DOTALL)
        texts[doc.doc_id] = (match.group(1) if match else doc.body).strip()
    return texts


def run_fingerprint(store: VectorStore) -> dict[str, Any]:
    provider = get_provider()
    settings = SETTINGS.retrieval
    return pipeline_fingerprint(
        provider.name, provider.model, getattr(store.embedder, "name", "unknown"),
        settings.kb_dir, settings.top_k, settings.min_relevance,
    )


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


def _tokens(final: dict[str, Any]) -> tuple[int, int, str]:
    inp = out = 0
    for event in final.get("agent_trace") or []:
        payload = event.get("payload") or {}
        inp += int(payload.get("input_tokens") or 0)
        out += int(payload.get("output_tokens") or 0)
    return inp, out, "approximate" if get_provider().name == "mock" else "reported"


def make_record(
    variant: str,
    ticket: EvalTicket,
    final: dict[str, Any],
    latency_ms: float,
    gold_texts: dict[str, str],
    seed: int | None = None,
) -> dict[str, Any]:
    retrieved = final.get("retrieved_docs") or []
    retrieved_ids = [str(d.get("doc_id")) for d in retrieved]
    gold_rank = (retrieved_ids.index(ticket.gold_doc_id) + 1) if ticket.gold_doc_id in retrieved_ids else None
    produced = answer_produced(final)
    checks = final.get("policy_checks") or {}
    in_tok, out_tok, token_count = _tokens(final)
    raw = float(final.get("confidence_score") or 0.0)
    basis = final.get("confidence_basis") or "raw"
    gate = float(final.get("calibrated_confidence") or 0.0) if basis == "calibrated" else raw
    rouge = None
    if produced and ticket.gold_doc_id and ticket.gold_doc_id in gold_texts:
        rouge = rouge_l_f1(" ".join(final.get("resolution_steps") or []), gold_texts[ticket.gold_doc_id])

    return {
        "variant": variant,
        "seed": seed,
        "ticket_id": ticket.ticket_id,
        "subset": ticket.subset,
        "adversarial_type": ticket.adversarial_type,
        "gold_category": ticket.gold_category,
        "gold_priority": ticket.gold_priority,
        "gold_doc_id": ticket.gold_doc_id,
        "should_escalate": ticket.should_escalate,
        "pred_category": final.get("category"),
        "pred_priority": final.get("priority"),
        "retrieved_ids": retrieved_ids,
        "retrieved_scores": [float(d.get("score", 0.0)) for d in retrieved],
        "top_relevance": float(final.get("top_relevance") or 0.0),
        "gold_rank": gold_rank,
        "grounded": bool(final.get("grounded")),
        "answer_produced": produced,
        "primary_citation": primary_citation(final) if produced else None,
        "answer_correct": answer_correct(final, ticket),
        "delivered": delivered(final),
        "needs_human": needs_human(final, ticket),
        "outcome_class": outcome_class(final, ticket),
        "confidence_raw": raw,
        "confidence_calibrated": (
            float(final.get("calibrated_confidence")) if final.get("confidence_is_calibrated") else None
        ),
        "confidence_basis": basis,
        "confidence_gate": gate,
        "threshold_applied": final.get("confidence_threshold_applied"),
        "verdict": final.get("governance_verdict"),
        "checks": checks,
        "eligible_except_g3": bool(checks) and all(checks.get(name, False) for name in NON_G3_CHECKS),
        "rouge_l": rouge,
        "latency_ms": latency_ms,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "token_count": token_count,
        "path": [str(e.get("agent")) for e in final.get("agent_trace") or []],
        "mast": annotate(
            TraceContext(
                variant=variant,
                final=final,
                ticket=ticket,
                min_relevance=SETTINGS.retrieval.min_relevance,
                naive_threshold=SETTINGS.governance.confidence_threshold,
            )
        ),
    }


# --------------------------------------------------------------------------- #
# Running variants
# --------------------------------------------------------------------------- #


@dataclass
class Harness:
    store: VectorStore
    gold_texts: dict[str, str]
    keep_finals: bool = False

    def __post_init__(self) -> None:
        set_default_store(self.store)  # every agent now searches this index
        self.finals: dict[tuple[str, str, int | None], dict[str, Any]] = {}

    def compile(self, variant: str, profile: CalibrationProfile | None = None):
        if variant == "single_agent":
            return build_single_agent_graph(store=self.store, threshold=SINGLE_AGENT_THRESHOLD).compile()
        if variant == "ungoverned":
            return build_ungoverned_graph().compile()
        if variant == "naive_governed":
            return build_graph("raw").compile()
        if variant == "calibration_governed":
            if profile is None:
                raise ValueError("calibration_governed needs a profile")
            return build_graph("calibrated", profile).compile()
        raise ValueError(f"unknown variant {variant!r}")

    def run(
        self,
        variant: str,
        tickets: Iterable[EvalTicket],
        profile: CalibrationProfile | None = None,
        seed: int | None = None,
    ) -> list[dict[str, Any]]:
        graph = self.compile(variant, profile)
        records = []
        for ticket in tickets:
            started = time.perf_counter()
            final = graph.invoke(new_state(ticket.text, ticket_id=ticket.ticket_id))
            latency = (time.perf_counter() - started) * 1000.0
            if self.keep_finals:
                self.finals[(variant, ticket.ticket_id, seed)] = final
            records.append(make_record(variant, ticket, final, latency, self.gold_texts, seed))
        return records


# --------------------------------------------------------------------------- #
# Calibration fitting (Weeks 8-12) from naively-governed calibration records
# --------------------------------------------------------------------------- #


def fit_profile(
    calibration_records: Sequence[dict[str, Any]],
    fingerprint: dict[str, Any],
    alpha: float,
    delta: float,
    method: str = "ltt",
    seed: int | None = None,
    n_bins: int = 10,
) -> tuple[CalibrationProfile, dict[str, Any]]:
    """Fit T on answered calibration tickets, then select the G3 threshold.

    ``calibration_records`` must come from the naively-governed variant (V3):
    its pipeline is identical to V4's up to check G3, so its raw confidences
    and its non-G3 check results are exactly what V4 will see.
    """
    answered = [r for r in calibration_records if r["answer_produced"]]
    raw = np.asarray([r["confidence_raw"] for r in answered], dtype=float)
    correct = np.asarray([1 if r["answer_correct"] else 0 for r in answered], dtype=float)
    scaler = TemperatureScaler().fit(raw, correct)
    calibrated = scaler.transform(raw)

    all_raw = np.asarray([r["confidence_raw"] for r in calibration_records], dtype=float)
    scores = scaler.transform(all_raw)
    unsafe = [1 if r["needs_human"] else 0 for r in calibration_records]
    eligible = [1 if r["eligible_except_g3"] else 0 for r in calibration_records]
    selection = select_threshold(scores, unsafe, eligible, alpha=alpha, delta=delta, method=method)

    diagnostics = {
        "n_calibration_tickets": len(calibration_records),
        "n_answered": len(answered),
        "temperature": scaler.to_dict(),
        "before": calibration_summary(raw, correct, n_bins),
        "after": calibration_summary(calibrated, correct, n_bins),
        "threshold_selection": selection.to_dict(),
        "raw_scores": [
            {"ticket_id": r["ticket_id"], "confidence_raw": r["confidence_raw"],
             "answer_correct": r["answer_correct"]} for r in answered
        ],
    }
    profile = CalibrationProfile(
        temperature=scaler.temperature,
        threshold=selection.threshold,
        alpha=alpha,
        delta=delta,
        feasible=selection.feasible,
        fingerprint=fingerprint,
        threshold_method=method,
        metrics={
            "ece_before": diagnostics["before"]["ece"],
            "ece_after": diagnostics["after"]["ece"],
            "brier_before": diagnostics["before"]["brier"],
            "brier_after": diagnostics["after"]["brier"],
            "nll_before": diagnostics["before"]["nll"],
            "nll_after": diagnostics["after"]["nll"],
            "auroc": diagnostics["before"]["auroc"],
            "temperature_at_search_bound": scaler.at_bound,
            "n_answered": len(answered),
            "calibration_coverage": selection.coverage,
            "calibration_unsafe_rate": selection.unsafe_resolution_rate,
            "calibration_unsafe_rate_upper_bound": selection.unsafe_rate_upper_bound,
        },
        split={"seed": seed, "n_calibration": len(calibration_records)},
    )
    return profile, diagnostics
