#!/usr/bin/env python3
"""Fit the calibration profile used by calibrated governance (Weeks 8-12).

Week 8-9  record the Resolution Agent's raw confidence on the calibration split,
          fit a single temperature (NLL), and measure ECE / reliability before
          and after on the calibration split and on the untouched test split.
Week 10-12 select the G3 escalation threshold on the calibration split with a
          finite-sample risk guarantee (Learn then Test, alpha / delta).

The profile is written to artifacts/calibration/<provider>__<embedder>.json,
where the pipeline's "auto" governance mode picks it up whenever the running
configuration matches its fingerprint.

Usage:
    python scripts/calibrate.py --embedder minilm
    python scripts/calibrate.py --embedder tfidf          # profile for the container image
    python scripts/calibrate.py --alpha 0.10 --delta 0.10 --method crc
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ops_agent.calibration.metrics import calibration_summary  # noqa: E402
from ops_agent.config import SETTINGS  # noqa: E402
from ops_agent.data import load_dataset, stratified_split  # noqa: E402
from ops_agent.evaluation import figures  # noqa: E402
from ops_agent.evaluation.harness import (  # noqa: E402
    Harness,
    build_eval_store,
    fit_profile,
    gold_resolution_texts,
    run_fingerprint,
)
from ops_agent.llm import get_provider  # noqa: E402


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in text.lower()).strip("-")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--embedder", default="minilm", choices=("minilm", "tfidf", "auto"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--alpha", type=float, default=SETTINGS.governance.risk_alpha)
    parser.add_argument("--delta", type=float, default=SETTINGS.governance.risk_delta)
    parser.add_argument("--method", default="ltt", choices=("ltt", "crc"))
    parser.add_argument("--profile-dir", default=str(SETTINGS.governance.calibration_path))
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)

    provider = get_provider()
    tickets = load_dataset()
    split = stratified_split(tickets, args.seed)
    store = build_eval_store(args.embedder)
    embedder = getattr(store.embedder, "name", args.embedder)
    harness = Harness(store, gold_resolution_texts())

    print(f"Provider {provider.name}:{provider.model} | embedder {embedder}")
    print(f"Calibration split: {len(split.calibration)} tickets (seed {args.seed})")
    cal_records = harness.run("naive_governed", split.calibration)
    profile, diag = fit_profile(cal_records, run_fingerprint(store), args.alpha, args.delta, args.method, args.seed)

    profile_dir = Path(args.profile_dir)
    if profile_dir.suffix == ".json":
        target = profile_dir
    else:
        target = profile_dir / f"{_slug(provider.name + '-' + provider.model)}__{_slug(embedder)}.json"
    profile.save(target)

    # Held-out check on the test split: does the temperature fitted on the
    # calibration split also lower ECE on tickets it never saw?
    test_records = harness.run("naive_governed", split.test)
    answered = [r for r in test_records if r["answer_produced"]]
    raw = [r["confidence_raw"] for r in answered]
    scaled = [profile.transform(value) for value in raw]
    correct = [1 if r["answer_correct"] else 0 for r in answered]
    test_before, test_after = calibration_summary(raw, correct), calibration_summary(scaled, correct)

    tag = f"{_slug(provider.name)}-{'minilm' if 'MiniLM' in embedder else 'tfidf'}"
    out = ROOT / "reports" / "calibration" / tag
    out.mkdir(parents=True, exist_ok=True)
    cal_answered = [r for r in cal_records if r["answer_produced"]]
    cal_raw = [r["confidence_raw"] for r in cal_answered]
    cal_correct = [1 if r["answer_correct"] else 0 for r in cal_answered]
    figures.reliability_diagram(
        (cal_raw, cal_correct), ([profile.transform(v) for v in cal_raw], cal_correct),
        f"Calibration split, raw (ECE {diag['before']['ece']:.3f})",
        f"Calibration split, T={profile.temperature:.2f} (ECE {diag['after']['ece']:.3f})",
        out / "reliability_calibration_split.png",
    )
    figures.reliability_diagram(
        (raw, correct), (scaled, correct),
        f"Test split, raw (ECE {test_before['ece']:.3f})",
        f"Test split, T={profile.temperature:.2f} (ECE {test_after['ece']:.3f})",
        out / "reliability_test_split.png",
    )
    with open(out / "raw_scores_calibration_split.csv", "w", encoding="utf-8", newline="\n") as handle:
        handle.write("ticket_id,confidence_raw,confidence_calibrated,answer_correct,eligible_except_g3,needs_human\n")
        for r in cal_records:
            handle.write(f"{r['ticket_id']},{r['confidence_raw']:.6f},{profile.transform(r['confidence_raw']):.6f},"
                         f"{int(r['answer_correct'])},{int(r['eligible_except_g3'])},{int(r['needs_human'])}\n")
    report = {
        "profile_path": str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target),
        "profile": profile.to_dict(),
        "calibration_split": {"before": diag["before"], "after": diag["after"]},
        "test_split": {"before": test_before, "after": test_after},
        "threshold_selection": diag["threshold_selection"],
    }
    (out / "calibration_report.json").write_text(json.dumps(report, indent=2, default=float) + "\n", encoding="utf-8")

    sel = diag["threshold_selection"]
    print(f"Temperature T      : {profile.temperature:.4f}")
    print(f"ECE calibration    : {diag['before']['ece']:.4f} -> {diag['after']['ece']:.4f}")
    print(f"ECE test (held out): {test_before['ece']:.4f} -> {test_after['ece']:.4f}")
    print(f"G3 threshold       : {profile.threshold:.3f} ({args.method.upper()}, alpha={args.alpha}, "
          f"delta={args.delta}, {'certified' if profile.feasible else 'NOT certifiable - fail closed'})")
    print(f"  calibration split: {sel['n_auto_resolved']} auto-resolved, {sel['unsafe_auto_resolved']} unsafe, "
          f"URR upper bound {sel['unsafe_rate_upper_bound']:.3f}")
    print(f"Profile            : {target} (id {profile.profile_id})")
    print(f"Reports            : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
