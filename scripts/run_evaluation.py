#!/usr/bin/env python3
"""Comparative evaluation of the four pipeline variants (synopsis Phase 7, Weeks 13-14).

Protocol (fixed before the run; see docs/research/ for the rationale)
  * Dataset: data/eval/dataset.jsonl (430 labeled tickets).
  * Repeated stratified 70:15:15 splits, seeds 42..(42 + n - 1). Seed 42 is the
    canonical split used for the confirmatory tests.
  * The calibration split fits the temperature and the G3 threshold (V4 only).
  * Primary population: every ticket NOT in the calibration split ("held-out",
    n = 366), i.e. the full dataset minus the data used for fitting. The 15%
    test split alone (n = 64) is reported as well.
  * Primary safety endpoint: Unsafe Resolution Rate (URR). Pre-specified
    hypotheses and tests are listed in the generated REPORT.md.

Usage:
    python scripts/run_evaluation.py --embedder minilm
    python scripts/run_evaluation.py --embedder tfidf --seeds 10
    OPS_LLM_PROVIDER=gemini python scripts/run_evaluation.py --embedder minilm --seeds 3
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ops_agent.calibration.metrics import calibration_summary  # noqa: E402
from ops_agent.config import SETTINGS  # noqa: E402
from ops_agent.data import load_dataset, stratified_split  # noqa: E402
from ops_agent.evaluation import figures  # noqa: E402
from ops_agent.evaluation.harness import (  # noqa: E402
    VARIANT_LABELS,
    VARIANTS,
    Harness,
    build_eval_store,
    fit_profile,
    gold_resolution_texts,
    run_fingerprint,
)
from ops_agent.evaluation.metrics import by_group, summarize  # noqa: E402
from ops_agent.evaluation.replay import replay  # noqa: E402
from ops_agent.evaluation.stats import (  # noqa: E402
    bootstrap_ci,
    cochran_q,
    holm,
    mcnemar_exact,
    paired_bootstrap_diff,
)
from ops_agent.evaluation.tracking import Tracker  # noqa: E402
from ops_agent.llm import get_provider  # noqa: E402
from ops_agent.mast.taxonomy import MODE_CODES, MODES_BY_CODE  # noqa: E402

KEY_METRICS = (
    "automation_rate",
    "correct_resolution_rate",
    "unsafe_resolution_rate",
    "unnecessary_escalation_rate",
    "mast_any_user_facing_rate",
)
SENSITIVITY_ALPHAS = (0.02, 0.05, 0.10, 0.15, 0.20)


def _pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{100 * value:.{digits}f}%"


def _num(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _pvalue(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _slim(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k not in ("retrieved_scores",)}


def _sweep(records: list[dict[str, Any]], confidence_key: str, eligible_key: str | None) -> tuple[list, list]:
    """Automation vs URR as the G3 threshold sweeps from 1.0 down to 0."""
    n = len(records)
    candidates = [r for r in records if (r[eligible_key] if eligible_key else r["answer_produced"])]
    candidates.sort(key=lambda r: -r[confidence_key])
    automation, urr, unsafe = [0.0], [0.0], 0
    for index, record in enumerate(candidates, start=1):
        unsafe += 1 if record["needs_human"] else 0
        automation.append(index / n)
        urr.append(unsafe / n)
    return automation, urr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--embedder", default="minilm", choices=("minilm", "tfidf", "auto"))
    parser.add_argument("--seeds", type=int, default=10, help="number of repeated splits")
    parser.add_argument("--first-seed", type=int, default=42)
    parser.add_argument("--alpha", type=float, default=SETTINGS.governance.risk_alpha)
    parser.add_argument("--delta", type=float, default=SETTINGS.governance.risk_delta)
    parser.add_argument("--method", default="ltt", choices=("ltt", "crc"))
    parser.add_argument("--out", default=str(ROOT / "reports" / "evaluation"))
    parser.add_argument("--mlflow", action="store_true", help="also log to MLflow if installed")
    args = parser.parse_args()

    logging.basicConfig(level=logging.ERROR)
    started = time.perf_counter()
    provider = get_provider()
    tickets = load_dataset()
    by_id = {t.ticket_id: t for t in tickets}
    store = build_eval_store(args.embedder)
    embedder_name = getattr(store.embedder, "name", args.embedder)
    tag = f"{provider.name}-{'minilm' if 'MiniLM' in embedder_name else 'tfidf'}"
    out = Path(args.out) / tag
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "profiles").mkdir(parents=True, exist_ok=True)

    print(f"Provider {provider.name}:{provider.model} | embedder {embedder_name} | {len(tickets)} tickets")
    harness = Harness(store, gold_resolution_texts())
    fingerprint = run_fingerprint(store)

    # ---- Split-independent variants ------------------------------------------ #
    base: dict[str, list[dict[str, Any]]] = {}
    for variant in ("single_agent", "ungoverned", "naive_governed"):
        t0 = time.perf_counter()
        base[variant] = harness.run(variant, tickets)
        print(f"  ran {variant:<22} on {len(tickets)} tickets in {time.perf_counter() - t0:.1f}s")

    seeds = list(range(args.first_seed, args.first_seed + args.seeds))
    canonical = seeds[0]
    per_seed: dict[int, Any] = {}
    canonical_v4: list[dict[str, Any]] = []
    canonical_profile = None
    canonical_diag: dict[str, Any] = {}
    replay_mismatches = 0

    for seed in seeds:
        split = stratified_split(tickets, seed)
        cal_ids = {t.ticket_id for t in split.calibration}
        test_ids = {t.ticket_id for t in split.test}
        heldout = [t for t in tickets if t.ticket_id not in cal_ids]
        heldout_ids = {t.ticket_id for t in heldout}

        cal_records = [r for r in base["naive_governed"] if r["ticket_id"] in cal_ids]
        profile, diag = fit_profile(cal_records, fingerprint, args.alpha, args.delta, args.method, seed)
        profile.save(out / "profiles" / f"seed{seed}.json")
        v4 = harness.run("calibration_governed", heldout, profile, seed)

        # Replay must reproduce the real V4 run exactly (pure governance).
        v3_heldout = [r for r in base["naive_governed"] if r["ticket_id"] in heldout_ids]
        replayed = {r["ticket_id"]: r["delivered"] for r in replay(v3_heldout, profile)}
        replay_mismatches += sum(1 for r in v4 if replayed[r["ticket_id"]] != r["delivered"])

        populations = {"heldout": heldout_ids, "test": test_ids}
        seed_result: dict[str, Any] = {"profile": profile.to_dict(), "calibration_fit": {
            k: v for k, v in diag.items() if k != "raw_scores"}}
        for name, ids in populations.items():
            seed_result[name] = {}
            for variant in VARIANTS:
                source = v4 if variant == "calibration_governed" else base[variant]
                seed_result[name][variant] = summarize([r for r in source if r["ticket_id"] in ids])
        per_seed[seed] = seed_result
        if seed == canonical:
            canonical_v4, canonical_profile, canonical_diag = v4, profile, diag
        heldout_urr = seed_result["heldout"]["calibration_governed"]["unsafe_resolution_rate"]
        print(f"  seed {seed}: T={profile.temperature:.3f} threshold={profile.threshold:.3f} "
              f"V4 held-out URR={heldout_urr:.3f} automation="
              f"{seed_result['heldout']['calibration_governed']['automation_rate']:.3f}")

    # ---- Canonical-split confirmatory analysis --------------------------------- #
    split = stratified_split(tickets, canonical)
    cal_ids = {t.ticket_id for t in split.calibration}
    heldout_order = [t.ticket_id for t in tickets if t.ticket_id not in cal_ids]
    canonical_records = {
        variant: {r["ticket_id"]: r for r in (canonical_v4 if variant == "calibration_governed" else base[variant])
                  if r["ticket_id"] in set(heldout_order)}
        for variant in VARIANTS
    }

    def outcome(variant: str, key: str) -> np.ndarray:
        rows = [canonical_records[variant][tid] for tid in heldout_order]
        if key == "unsafe":
            return np.array([r["outcome_class"] == "unsafe_resolution" for r in rows])
        if key == "correct":
            return np.array([r["outcome_class"] == "correct_resolution" for r in rows])
        if key == "mast":
            return np.array([any(r["mast"][c]["user_facing"] for c in MODE_CODES) for r in rows])
        raise KeyError(key)

    tests: dict[str, Any] = {}
    for key, label in (("unsafe", "Unsafe autonomous resolution"), ("correct", "Correct autonomous resolution"),
                       ("mast", "Any user-facing MAST failure")):
        matrix = np.column_stack([outcome(v, key) for v in VARIANTS]).astype(int)
        pairwise = {}
        for other in ("single_agent", "ungoverned", "naive_governed"):
            res = mcnemar_exact(outcome("calibration_governed", key), outcome(other, key))
            diff = paired_bootstrap_diff(outcome("calibration_governed", key), outcome(other, key), seed=7)
            pairwise[other] = {**res, **diff}
        adjusted = holm([pairwise[o]["p_value"] for o in pairwise])
        for other, p_adj in zip(pairwise, adjusted):
            pairwise[other]["p_holm"] = p_adj
        tests[key] = {"label": label, "cochran_q": cochran_q(matrix), "v4_vs": pairwise,
                      "rates": {v: float(outcome(v, key).mean()) for v in VARIANTS}}

    intervals: dict[str, Any] = {}
    for variant in VARIANTS:
        intervals[variant] = {
            "unsafe_resolution_rate": bootstrap_ci(outcome(variant, "unsafe").astype(float), seed=11),
            "correct_resolution_rate": bootstrap_ci(outcome(variant, "correct").astype(float), seed=11),
            "mast_any_user_facing_rate": bootstrap_ci(outcome(variant, "mast").astype(float), seed=11),
        }

    # ---- Aggregation across repeated splits ----------------------------------- #
    aggregate: dict[str, Any] = {}
    for population in ("heldout", "test"):
        aggregate[population] = {}
        for variant in VARIANTS:
            aggregate[population][variant] = {}
            for metric in KEY_METRICS + ("ece_gate",):
                values = [
                    per_seed[s][population][variant]["calibration"]["ece"] if metric == "ece_gate"
                    else per_seed[s][population][variant][metric]
                    for s in seeds
                ]
                values = [v for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
                aggregate[population][variant][metric] = {
                    "mean": float(np.mean(values)) if values else None,
                    "sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                    "min": float(np.min(values)) if values else None,
                    "max": float(np.max(values)) if values else None,
                }
    guarantee = {
        "alpha": args.alpha, "delta": args.delta, "method": args.method,
        "splits": len(seeds),
        "splits_with_heldout_urr_above_alpha": sum(
            1 for s in seeds if per_seed[s]["heldout"]["calibration_governed"]["unsafe_resolution_rate"] > args.alpha),
        "splits_with_test_urr_above_alpha": sum(
            1 for s in seeds if per_seed[s]["test"]["calibration_governed"]["unsafe_resolution_rate"] > args.alpha),
        "splits_infeasible": sum(1 for s in seeds if not per_seed[s]["profile"]["feasible"]),
        "temperatures": [per_seed[s]["profile"]["temperature"] for s in seeds],
        "thresholds": [per_seed[s]["profile"]["threshold"] for s in seeds],
    }

    # ---- Sensitivity to alpha and to the selection method (replay) ------------- #
    cal_records = [r for r in base["naive_governed"] if r["ticket_id"] in cal_ids]
    v3_heldout = [canonical_records["naive_governed"][tid] for tid in heldout_order]
    sensitivity: list[dict[str, Any]] = []
    for method in ("ltt", "crc"):
        for alpha in SENSITIVITY_ALPHAS:
            profile, _ = fit_profile(cal_records, fingerprint, alpha, args.delta, method, canonical)
            rows = replay(v3_heldout, profile)
            n = len(rows)
            sensitivity.append({
                "method": method, "alpha": alpha, "threshold": profile.threshold, "feasible": profile.feasible,
                "automation_rate": sum(r["delivered"] for r in rows) / n,
                "unsafe_resolution_rate": sum(r["outcome_class"] == "unsafe_resolution" for r in rows) / n,
                "correct_resolution_rate": sum(r["outcome_class"] == "correct_resolution" for r in rows) / n,
            })

    # ---- Calibration on held-out answers (canonical) --------------------------- #
    answered = [r for r in v3_heldout if r["answer_produced"]]
    raw_conf = [r["confidence_raw"] for r in answered]
    cal_conf = [canonical_profile.transform(c) for c in raw_conf]
    correct = [1 if r["answer_correct"] else 0 for r in answered]
    heldout_calibration = {"raw": calibration_summary(raw_conf, correct), "calibrated": calibration_summary(cal_conf, correct)}
    single_answered = [canonical_records["single_agent"][tid] for tid in heldout_order
                       if canonical_records["single_agent"][tid]["answer_produced"]]
    heldout_calibration["single_agent_raw"] = calibration_summary(
        [r["confidence_raw"] for r in single_answered], [1 if r["answer_correct"] else 0 for r in single_answered])

    # ---- Figures --------------------------------------------------------------- #
    canon = per_seed[canonical]["heldout"]
    figures.reliability_diagram(
        (raw_conf, correct), (cal_conf, correct),
        f"Raw confidence (ECE {heldout_calibration['raw']['ece']:.3f})",
        f"Temperature-scaled, T={canonical_profile.temperature:.2f} (ECE {heldout_calibration['calibrated']['ece']:.3f})",
        out / "figures" / "reliability_diagram.png",
    )
    figures.outcome_composition(canon, VARIANT_LABELS, out / "figures" / "outcome_composition.png")
    figures.metric_bars(
        {v: canon[v]["unsafe_resolution_rate"] for v in VARIANTS},
        {v: intervals[v]["unsafe_resolution_rate"] for v in VARIANTS},
        VARIANT_LABELS, "Unsafe Resolution Rate (held-out, 95% bootstrap CI)",
        out / "figures" / "unsafe_resolution_rate.png", reference=args.alpha, reference_label=f"alpha = {args.alpha:.0%}",
    )
    figures.metric_bars(
        {v: canon[v]["correct_resolution_rate"] for v in VARIANTS},
        {v: intervals[v]["correct_resolution_rate"] for v in VARIANTS},
        VARIANT_LABELS, "Correct autonomous resolution (held-out, 95% CI)",
        out / "figures" / "correct_resolution_rate.png",
    )
    v1_rows = [canonical_records["single_agent"][tid] for tid in heldout_order]
    for row in v1_rows:
        row.setdefault("eligible_single", row["answer_produced"])
    curves = {
        "single_agent": _sweep(v1_rows, "confidence_raw", None),
        "naive_governed": _sweep(v3_heldout, "confidence_raw", "eligible_except_g3"),
    }
    points = {
        "single_agent": (canon["single_agent"]["automation_rate"], canon["single_agent"]["unsafe_resolution_rate"],
                         "V1 @ raw 0.70"),
        "naive_governed": (canon["naive_governed"]["automation_rate"], canon["naive_governed"]["unsafe_resolution_rate"],
                           "V3 @ raw 0.70"),
        "calibration_governed": (canon["calibration_governed"]["automation_rate"],
                                 canon["calibration_governed"]["unsafe_resolution_rate"],
                                 f"V4 @ calibrated {canonical_profile.threshold:.3f}"),
    }
    curve_labels = {"single_agent": "V1 threshold sweep", "naive_governed": "V3/V4 threshold sweep (same ranking)"}
    figures.risk_coverage(curves, points, {**VARIANT_LABELS, **curve_labels}, out / "figures" / "risk_coverage.png",
                          alpha=args.alpha)
    names = {c: MODES_BY_CODE[c].name for c in MODE_CODES}
    figures.mast_heatmap({v: {c: canon[v]["mast"][c]["user_facing_rate"] for c in MODE_CODES} for v in VARIANTS},
                         MODE_CODES, names, VARIANT_LABELS, "MAST failures that reached the user (held-out)",
                         out / "figures" / "mast_user_facing.png")
    figures.mast_heatmap({v: {c: canon[v]["mast"][c]["occurrence_rate"] for c in MODE_CODES} for v in VARIANTS},
                         MODE_CODES, names, VARIANT_LABELS, "MAST failures anywhere in the trace (held-out)",
                         out / "figures" / "mast_occurrence.png")
    ltt = [row for row in sensitivity if row["method"] == "ltt"]
    figures.sensitivity([r["alpha"] for r in ltt], [r["automation_rate"] for r in ltt],
                        [r["unsafe_resolution_rate"] for r in ltt], out / "figures" / "alpha_sensitivity.png")

    # ---- Persist -------------------------------------------------------------- #
    by_type = {v: by_group([canonical_records[v][tid] for tid in heldout_order], "adversarial_type") for v in VARIANTS}
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": f"{provider.name}:{provider.model}",
        "embedder": embedder_name,
        "fingerprint": fingerprint,
        "n_tickets": len(tickets),
        "seeds": seeds,
        "canonical_seed": canonical,
        "alpha": args.alpha, "delta": args.delta, "method": args.method,
        "canonical": {"heldout": canon, "test": per_seed[canonical]["test"],
                      "n_heldout": len(heldout_order), "tests": tests, "intervals": intervals,
                      "by_adversarial_type": by_type, "heldout_calibration": heldout_calibration,
                      "calibration_fit": {k: v for k, v in canonical_diag.items() if k != "raw_scores"},
                      "profile": canonical_profile.to_dict()},
        "aggregate": aggregate,
        "guarantee_check": guarantee,
        "sensitivity": sensitivity,
        "replay_mismatches": replay_mismatches,
        "per_seed": {str(s): {"profile": per_seed[s]["profile"],
                              "heldout": {v: {m: per_seed[s]["heldout"][v][m] for m in KEY_METRICS} for v in VARIANTS},
                              "test": {v: {m: per_seed[s]["test"][v][m] for m in KEY_METRICS} for v in VARIANTS}}
                     for s in seeds},
        "runtime_seconds": time.perf_counter() - started,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n", encoding="utf-8")
    with open(out / f"records_seed{canonical}.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for variant in VARIANTS:
            for tid in heldout_order:
                handle.write(json.dumps(_slim(canonical_records[variant][tid]), default=float) + "\n")
    with open(out / f"calibration_raw_scores_seed{canonical}.csv", "w", encoding="utf-8", newline="\n") as handle:
        handle.write("ticket_id,confidence_raw,confidence_calibrated,answer_correct\n")
        for row in canonical_diag["raw_scores"]:
            handle.write(f"{row['ticket_id']},{row['confidence_raw']:.6f},"
                         f"{canonical_profile.transform(row['confidence_raw']):.6f},{int(row['answer_correct'])}\n")

    write_report(out, summary, per_seed, seeds)
    Tracker(enabled=args.mlflow).log_run(tag, summary, out)
    print(f"Replay mismatches: {replay_mismatches}")
    print(f"Wrote {out / 'REPORT.md'} in {time.perf_counter() - started:.1f}s")
    return 0 if replay_mismatches == 0 else 1


# --------------------------------------------------------------------------- #
# Markdown report
# --------------------------------------------------------------------------- #


def write_report(out: Path, s: dict[str, Any], per_seed: dict[int, Any], seeds: list[int]) -> None:
    c = s["canonical"]
    h = c["heldout"]
    L = VARIANT_LABELS
    lines: list[str] = []
    add = lines.append
    add(f"# OPS-AGENT comparative evaluation - {s['provider']} / {s['embedder']}\n")
    add(f"Generated {s['generated_at']} by `scripts/run_evaluation.py`. All numbers below are read from "
        f"`summary.json` in this folder.\n")
    add("## Protocol\n")
    add(f"* {s['n_tickets']} labeled tickets (`data/eval/dataset.jsonl`); stratified 70:15:15 splits, "
        f"{len(seeds)} repetitions (seeds {seeds[0]}-{seeds[-1]}); canonical seed {s['canonical_seed']}.")
    add(f"* V4 fits one temperature and selects its G3 threshold on the calibration split only "
        f"({s['method'].upper()}, alpha = {s['alpha']}, delta = {s['delta']}).")
    add(f"* Primary population: held-out tickets = every ticket not in the calibration split "
        f"(n = {c['n_heldout']}). The 15% test split is reported separately.")
    add(f"* Replay check: re-deciding V3 traces under each V4 profile reproduced the real V4 runs with "
        f"{s['replay_mismatches']} mismatches.\n")
    add("### Pre-specified hypotheses\n")
    add("* **H1** V4 has a lower Unsafe Resolution Rate (URR) than V1 (single agent, raw threshold 0.70).")
    add("* **H2** V4 has a lower URR than V3 (naively governed, raw threshold 0.70).")
    add("* **H3** V4 has a lower rate of user-facing MAST failures than V1 and V2.")
    add("* **H4** Temperature scaling lowers the Expected Calibration Error on held-out tickets.")
    add(f"* **H5** The risk guarantee holds: V4's held-out URR exceeds alpha in at most "
        f"{s['delta']:.0%} of repeated splits.\n")

    add("## Main results (canonical split, held-out tickets)\n")
    add("| Variant | Automation | Correct autonomous | URR [95% CI] | Unnecessary escalation | "
        "Escalation recall | Answer accuracy (documented tickets) | ECE (gate) | User-facing MAST [95% CI] |")
    add("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for v in VARIANTS:
        m = h[v]
        ci = c["intervals"][v]["unsafe_resolution_rate"]
        mci = c["intervals"][v]["mast_any_user_facing_rate"]
        add(f"| {L[v]} | {_pct(m['automation_rate'])} | {_pct(m['correct_resolution_rate'])} | "
            f"{_pct(m['unsafe_resolution_rate'])} [{_pct(ci[0])}, {_pct(ci[1])}] | "
            f"{_pct(m['unnecessary_escalation_rate'])} | {_pct(m['escalation']['recall'])} | "
            f"{_pct(m['resolution_quality']['answer_accuracy_when_answered'])} | "
            f"{_num(m['calibration'].get('ece'))} | {_pct(m['mast_any_user_facing_rate'])} "
            f"[{_pct(mci[0])}, {_pct(mci[1])}] |")
    add("\nOutcome counts:\n")
    add("| Variant | Correct autonomous | Unsafe autonomous | Necessary escalation | Unnecessary escalation |")
    add("|---|---:|---:|---:|---:|")
    for v in VARIANTS:
        o = h[v]["outcomes"]
        add(f"| {L[v]} | {o['correct_resolution']} | {o['unsafe_resolution']} | "
            f"{o['necessary_escalation']} | {o['unnecessary_escalation']} |")

    add("\n## Statistical tests (canonical split, held-out, paired)\n")
    for key, block in c["tests"].items():
        q = block["cochran_q"]
        add(f"**{block['label']}** - Cochran's Q = {q['q']:.2f}, df = {q['df']}, p = {_pvalue(q['p_value'])}.\n")
        add("| V4 vs | Rate V4 | Rate other | Difference [95% CI] | Only V4 | Only other | McNemar p | Holm p |")
        add("|---|---:|---:|---:|---:|---:|---:|---:|")
        for other, r in block["v4_vs"].items():
            add(f"| {L[other]} | {_pct(block['rates']['calibration_governed'])} | {_pct(block['rates'][other])} | "
                f"{_pct(r['difference'])} [{_pct(r['ci_low'])}, {_pct(r['ci_high'])}] | {r['only_first']} | "
                f"{r['only_second']} | {_pvalue(r['p_value'])} | {_pvalue(r['p_holm'])} |")
        if key == "mast":
            add("\nNote: under this project's operationalisation every failure that reaches the user is, by "
                "definition, also an unsafe autonomous resolution (FM-3.2/3.3 label exactly the flawed "
                "deliveries), so this aggregate test mirrors the URR test above. The informative MAST result is "
                "the per-mode table further down: which failures occur upstream, and which ones each variant "
                "lets through.")
        add("")

    add("## Calibration (Weeks 8-9)\n")
    fit = c["calibration_fit"]
    add(f"Fitted on {fit['n_answered']} answered calibration tickets: T = {fit['temperature']['temperature']:.4f}.\n")
    add("| Confidence | n | Accuracy | Mean confidence | ECE | MCE | Brier | NLL | AUROC |")
    add("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name, block in (("Calibration split - raw", fit["before"]), ("Calibration split - scaled", fit["after"]),
                        ("Held-out - raw (V3/V4 answers)", c["heldout_calibration"]["raw"]),
                        ("Held-out - scaled (V4)", c["heldout_calibration"]["calibrated"]),
                        ("Held-out - V1 single agent raw", c["heldout_calibration"]["single_agent_raw"])):
        add(f"| {name} | {block['n']} | {_pct(block['accuracy'])} | {_num(block['mean_confidence'])} | "
            f"{_num(block['ece'])} | {_num(block['mce'])} | {_num(block['brier'])} | {_num(block['nll'])} | "
            f"{_num(block['auroc'])} |")
    sel = fit["threshold_selection"]
    add(f"\nThreshold selection ({sel['method'].upper()}): threshold = {sel['threshold']:.3f} "
        f"({'certified' if sel['feasible'] else 'NOT certifiable - fail closed'}); on the calibration split it "
        f"auto-resolves {sel['n_auto_resolved']} of {sel['n_calibration']} tickets with "
        f"{sel['unsafe_auto_resolved']} unsafe (URR upper bound {_pct(sel['unsafe_rate_upper_bound'])} at "
        f"{1 - sel['delta']:.0%} confidence).\n")

    add("## Robustness across repeated splits\n")
    add("| Variant | Population | Automation mean (sd) | URR mean (sd) | URR max | Correct autonomous mean |")
    add("|---|---|---:|---:|---:|---:|")
    for population in ("heldout", "test"):
        for v in VARIANTS:
            a = s["aggregate"][population][v]
            add(f"| {L[v]} | {population} | {_pct(a['automation_rate']['mean'])} ({_pct(a['automation_rate']['sd'])}) | "
                f"{_pct(a['unsafe_resolution_rate']['mean'])} ({_pct(a['unsafe_resolution_rate']['sd'])}) | "
                f"{_pct(a['unsafe_resolution_rate']['max'])} | {_pct(a['correct_resolution_rate']['mean'])} |")
    g = s["guarantee_check"]
    add(f"\nGuarantee check (H5): V4 held-out URR exceeded alpha = {g['alpha']} in "
        f"{g['splits_with_heldout_urr_above_alpha']} of {g['splits']} splits "
        f"(test split only: {g['splits_with_test_urr_above_alpha']} of {g['splits']}); "
        f"{g['splits_infeasible']} split(s) could not certify any threshold. Temperatures ranged "
        f"{min(g['temperatures']):.3f}-{max(g['temperatures']):.3f}; thresholds "
        f"{min(g['thresholds']):.3f}-{max(g['thresholds']):.3f}.\n")

    add("## Sensitivity to the risk target (canonical split, replayed)\n")
    add("| Method | alpha | Threshold | Certified | Automation | URR | Correct autonomous |")
    add("|---|---:|---:|---|---:|---:|---:|")
    for row in s["sensitivity"]:
        add(f"| {row['method'].upper()} | {row['alpha']:.2f} | {row['threshold']:.3f} | "
            f"{'yes' if row['feasible'] else 'no'} | {_pct(row['automation_rate'])} | "
            f"{_pct(row['unsafe_resolution_rate'])} | {_pct(row['correct_resolution_rate'])} |")

    add("\n## Resolution quality and classification (held-out)\n")
    add("| Variant | Retrieval recall@k | MRR | Top-1 answer accuracy | ROUGE-L | Category acc. | "
        "Category macro-F1 | Priority acc. |")
    add("|---|---:|---:|---:|---:|---:|---:|---:|")
    for v in VARIANTS:
        rq, cl = h[v]["resolution_quality"], h[v]["classification"]
        add(f"| {L[v]} | {_pct(rq['retrieval_recall_at_k'])} | {_num(rq['retrieval_mrr'])} | "
            f"{_pct(rq['top1_accuracy'])} | {_num(rq['rouge_l_mean'])} | {_pct(cl['category_accuracy'])} | "
            f"{_num(cl['category_macro_f1'])} | {_pct(cl['priority_accuracy'])} |")

    add("\n## MAST failure modes (held-out; occurred / reached the user)\n")
    add("| Mode | " + " | ".join(L[v] for v in VARIANTS) + " |")
    add("|---|" + "---:|" * len(VARIANTS))
    for code in MODE_CODES:
        cells = []
        for v in VARIANTS:
            m = h[v]["mast"][code]
            cells.append("n/a" if m["applicable"] == 0 else f"{m['occurred']} / {m['user_facing']}")
        add(f"| {code} {MODES_BY_CODE[code].name} | " + " | ".join(cells) + " |")
    add("| Any failure (traces) | " + " | ".join(
        f"{_pct(h[v]['mast_any_failure_rate'])} / {_pct(h[v]['mast_any_user_facing_rate'])}" for v in VARIANTS) + " |")

    add("\n## Unsafe Resolution Rate by ticket type (held-out)\n")
    types = sorted(c["by_adversarial_type"]["ungoverned"])
    add("| Type | n | " + " | ".join(L[v] for v in VARIANTS) + " |")
    add("|---|---:|" + "---:|" * len(VARIANTS))
    for t in types:
        n = c["by_adversarial_type"]["ungoverned"][t]["n"]
        add(f"| {t} | {n} | " + " | ".join(_pct(c["by_adversarial_type"][v][t]["unsafe_resolution_rate"])
                                          for v in VARIANTS) + " |")

    add("\n## Cost and latency (held-out)\n")
    add("| Variant | Tokens / ticket | Projected cost / 1,000 tickets | Mean latency | p95 latency |")
    add("|---|---:|---:|---:|---:|")
    for v in VARIANTS:
        cost, lat = h[v]["cost"], h[v]["latency_ms"]
        add(f"| {L[v]} | {cost['tokens_per_ticket']:.0f} | ${cost['projected_cost_usd_per_1000_tickets']:.2f} "
            f"({cost['projection_model']}) | {lat['mean']:.1f} ms | {lat['p95']:.1f} ms |")
    add("\nToken counts under the offline provider are estimates (4 characters per token); the projected "
        "cost prices those counts at the Gemini list price. Latency is wall-clock on the evaluation machine.\n")

    add("## Figures\n")
    for name, caption in (("outcome_composition.png", "Outcome composition per variant"),
                          ("unsafe_resolution_rate.png", "Unsafe Resolution Rate with 95% bootstrap CIs"),
                          ("correct_resolution_rate.png", "Correct autonomous resolutions with 95% CIs"),
                          ("risk_coverage.png", "Automation vs URR as the threshold sweeps; operating points marked"),
                          ("reliability_diagram.png", "Reliability diagram, raw vs temperature-scaled"),
                          ("mast_user_facing.png", "MAST failures that reached the user"),
                          ("mast_occurrence.png", "MAST failures anywhere in the trace"),
                          ("alpha_sensitivity.png", "V4 automation and URR against the risk target alpha")):
        add(f"![{caption}](figures/{name})\n")
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
