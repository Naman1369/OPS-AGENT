#!/usr/bin/env python3
"""MAST human-annotation kit (synopsis Phase 6, Weeks 10-12).

The synopsis protocol: two annotators independently label 100-150 execution
traces with the 14 MAST failure modes; agreement is measured with Cohen's
kappa; an LLM annotator is validated against the human labels and only then
used on the remaining traces. This script supports each step. It never fills
in human labels - those have to come from people.

    # 1. Draw a stratified sample of traces and write one blank sheet per annotator
    python scripts/mast_labeling_kit.py sample --n 120 --embedder minilm

    # 2. Annotators fill reports/mast/annotator_A.csv and annotator_B.csv (0/1 per mode)

    # 3. Agreement: human-human, and each human vs the rule-based annotator
    python scripts/mast_labeling_kit.py agreement

    # 4. (optional, needs GEMINI_API_KEY) LLM annotator on the same sample, then agreement
    OPS_LLM_PROVIDER=gemini python scripts/mast_labeling_kit.py llm
    python scripts/mast_labeling_kit.py agreement
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ops_agent.data import load_dataset  # noqa: E402
from ops_agent.evaluation.harness import VARIANTS, Harness, build_eval_store, gold_resolution_texts  # noqa: E402
from ops_agent.mast.agreement import agreement_report  # noqa: E402
from ops_agent.mast.taxonomy import FAILURE_MODES, MODE_CODES  # noqa: E402

OUT = ROOT / "reports" / "mast"


def _display_id(trace_id: str) -> str:
    """Opaque, deterministic id so annotators cannot read the variant off the sheet."""
    return "T-" + hashlib.sha1(trace_id.encode("utf-8")).hexdigest()[:8].upper()


def _trace_text(final: dict) -> str:
    lines = []
    for event in final.get("agent_trace") or []:
        payload = json.dumps(event.get("payload") or {}, default=str)
        lines.append(f"[{event.get('agent')}:{event.get('event')}] {payload[:600]}")
    lines.append(f"FINAL RESPONSE: {(final.get('final_response') or '')[:900]}")
    return "\n".join(lines)


def cmd_sample(args) -> int:
    tickets = load_dataset()
    rng = random.Random(args.seed)
    harness = Harness(build_eval_store(args.embedder), gold_resolution_texts(), keep_finals=True)
    # Stratify: equal share per variant, and within it a mix of in-KB and adversarial tickets.
    per_variant = max(1, args.n // len(VARIANTS))
    sample = []
    from ops_agent.evaluation.harness import fit_profile, run_fingerprint
    from ops_agent.data import stratified_split

    split = stratified_split(tickets, 42)
    cal_ids = {t.ticket_id for t in split.calibration}
    heldout = [t for t in tickets if t.ticket_id not in cal_ids]
    cal_records = harness.run("naive_governed", split.calibration)
    profile, _ = fit_profile(cal_records, run_fingerprint(harness.store), 0.05, 0.10)
    for variant in VARIANTS:
        chosen = rng.sample(heldout, per_variant)
        records = harness.run(variant, chosen, profile if variant == "calibration_governed" else None)
        for ticket, record in zip(chosen, records):
            final = harness.finals[(variant, ticket.ticket_id, None)]
            sample.append((f"{variant}:{ticket.ticket_id}", variant, ticket, final, record))
    rng.shuffle(sample)  # annotators must not see variants in blocks

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "sample_traces.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for trace_id, variant, ticket, final, record in sample:
            handle.write(json.dumps({
                "trace_id": trace_id, "variant": variant, "ticket": ticket.to_dict(),
                "trace": _trace_text(final), "rule_labels": {c: bool(record["mast"][c]["occurred"]) for c in MODE_CODES},
            }, default=str) + "\n")
    header = ["trace_id", "ticket_text", "gold_doc_id", "should_escalate", "trace"] + list(MODE_CODES) + ["notes"]
    for annotator in ("A", "B"):
        with open(OUT / f"annotator_{annotator}.csv", "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for trace_id, _variant, ticket, final, _record in sample:
                # The variant name is hidden inside the trace text only through agent names;
                # the rule-based labels are NOT shown, so annotators are not anchored.
                writer.writerow([_display_id(trace_id),
                                 ticket.text, ticket.gold_doc_id or "", int(ticket.should_escalate),
                                 _trace_text(final)] + [""] * len(MODE_CODES) + [""])
    with open(OUT / "trace_key.json", "w", encoding="utf-8") as handle:
        json.dump({_display_id(trace_id): trace_id for trace_id, *_ in sample}, handle, indent=1)
    (OUT / "CODEBOOK.md").write_text(
        "# MAST codebook for OPS-AGENT traces\n\nMark 1 if the failure mode occurred anywhere in the trace, "
        "0 otherwise. Label independently; do not discuss until both sheets are complete.\n\n"
        + "\n".join(f"* **{m.code} {m.name}** ({m.category}) - {m.definition} *Project operationalisation:* "
                    f"{m.operationalisation}" for m in FAILURE_MODES) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(sample)} traces to {OUT} (annotator_A.csv, annotator_B.csv, CODEBOOK.md)")
    return 0


def _read_sheet(path: Path, key: dict[str, str]) -> dict[str, dict[str, bool]]:
    labels = {}
    with open(path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if all((row.get(code) or "").strip() == "" for code in MODE_CODES):
                continue  # not yet labeled
            labels[key.get(row["trace_id"], row["trace_id"])] = {
                code: (row.get(code) or "0").strip() in ("1", "true", "True", "yes") for code in MODE_CODES
            }
    return labels


def cmd_agreement(args) -> int:
    key = json.loads((OUT / "trace_key.json").read_text(encoding="utf-8"))
    rules = {}
    llm = {}
    with open(OUT / "sample_traces.jsonl", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            rules[row["trace_id"]] = row["rule_labels"]
            if "llm_labels" in row:
                llm[row["trace_id"]] = row["llm_labels"]
    a = _read_sheet(OUT / "annotator_A.csv", key)
    b = _read_sheet(OUT / "annotator_B.csv", key)
    report = {}
    common = sorted(set(a) & set(b))
    if common:
        report["human_A_vs_human_B"] = agreement_report([a[t] for t in common], [b[t] for t in common], MODE_CODES)
        for name, other in (("rules", rules), ("llm", llm)):
            both = [t for t in common if t in other]
            if both:
                report[f"human_A_vs_{name}"] = agreement_report([a[t] for t in both], [other[t] for t in both], MODE_CODES)
                report[f"human_B_vs_{name}"] = agreement_report([b[t] for t in both], [other[t] for t in both], MODE_CODES)
    else:
        print("No trace has been labeled by both annotators yet.")
    (OUT / "agreement.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, block in report.items():
        print(f"{name:<24} pooled kappa = {block['pooled_kappa']} ({block['pooled_interpretation']}), "
              f"n = {block['n_traces']}")
    return 0


def cmd_llm(args) -> int:
    from ops_agent.llm import get_provider
    from ops_agent.mast.llm_annotator import LLMAnnotator

    annotator = LLMAnnotator(get_provider())
    rows = [json.loads(line) for line in open(OUT / "sample_traces.jsonl", encoding="utf-8")]
    # Re-run each sampled trace deterministically to recover its full state.
    tickets = {t.ticket_id: t for t in load_dataset()}
    harness = Harness(build_eval_store(args.embedder), gold_resolution_texts(), keep_finals=True)
    for row in rows:
        variant, ticket_id = row["trace_id"].split(":")
        if variant == "calibration_governed":
            continue  # needs the profile; label V1-V3 traces, or extend as required
        harness.run(variant, [tickets[ticket_id]])
        final = harness.finals[(variant, ticket_id, None)]
        row["llm_labels"] = annotator.annotate(final, tickets[ticket_id])["labels"]
    with open(OUT / "sample_traces.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")
    print(f"LLM labels added for {sum('llm_labels' in r for r in rows)} traces")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.ERROR)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sample")
    p.add_argument("--n", type=int, default=120)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--embedder", default="minilm", choices=("minilm", "tfidf", "auto"))
    sub.add_parser("agreement")
    p = sub.add_parser("llm")
    p.add_argument("--embedder", default="minilm", choices=("minilm", "tfidf", "auto"))
    args = parser.parse_args()
    return {"sample": cmd_sample, "agreement": cmd_agreement, "llm": cmd_llm}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
