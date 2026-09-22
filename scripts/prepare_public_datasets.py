#!/usr/bin/env python3
"""Prepare the public Kaggle ticket datasets named in the synopsis (Phase 2).

The CSVs are not redistributed with this repository. Download them first
(needs a Kaggle API token in ~/.kaggle/kaggle.json):

    kaggle datasets download -d adisongoh/it-service-ticket-classification-dataset -p data/raw --unzip
    kaggle datasets download -d tobiasbueck/multilingual-customer-support-tickets -p data/raw --unzip

Then:

    python scripts/prepare_public_datasets.py                 # clean, dedup, split 70:15:15
    python scripts/prepare_public_datasets.py --evaluate 300  # + Intake agreement on a sample

Outputs go to data/processed/ (git-ignored): one JSONL per dataset and split,
plus a short report. These datasets carry no knowledge-base labels, so they
measure Intake classification agreement and out-of-distribution behaviour
(how often the governed pipeline escalates tickets its knowledge base cannot
answer) - not answer correctness.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ops_agent.data.public_datasets import deduplicate, load_bueck, load_goh  # noqa: E402

RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"


def _find(patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        matches = sorted(RAW.rglob(pattern))
        if matches:
            return matches[0]
    return None


def _split(rows: list, seed: int) -> dict[str, list]:
    rng = random.Random(seed)
    rows = list(rows)
    rng.shuffle(rows)
    n = len(rows)
    a, b = round(n * 0.70), round(n * 0.85)
    return {"train": rows[:a], "calibration": rows[a:b], "test": rows[b:]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--evaluate", type=int, default=0, help="run Intake + pipeline on N test tickets")
    args = parser.parse_args()

    sources = {
        "goh": (_find(("all_tickets_processed_improved_v3.csv", "*ticket*classification*.csv", "*tickets*processed*.csv")),
                load_goh),
        "bueck": (_find(("*dataset-tickets*.csv", "*customer*support*ticket*.csv")), load_bueck),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict[str, dict] = {}
    for name, (path, loader) in sources.items():
        if path is None:
            print(f"[skip] {name}: no CSV found under {RAW} (see the download commands in this script)")
            continue
        rows = loader(path)
        unique = deduplicate(rows)
        parts = _split(unique, args.seed)
        for split, items in parts.items():
            with open(OUT / f"public_{name}_{split}.jsonl", "w", encoding="utf-8", newline="\n") as handle:
                for item in items:
                    handle.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
        report[name] = {
            "source_file": str(path.relative_to(ROOT)),
            "rows": len(rows),
            "after_dedup": len(unique),
            "splits": {k: len(v) for k, v in parts.items()},
            "category_labels": dict(Counter(r.label_category for r in unique)),
            "priority_labels": dict(Counter(r.label_priority for r in unique)),
        }
        print(f"[ok] {name}: {len(rows)} rows, {len(unique)} after dedup -> {report[name]['splits']}")

        if args.evaluate and parts["test"]:
            from ops_agent.graph import compile_pipeline
            from ops_agent.state import new_state

            pipeline = compile_pipeline()
            sample = parts["test"][: args.evaluate]
            agree_cat = agree_pri = labeled_cat = labeled_pri = escalated = 0
            for ticket in sample:
                final = pipeline.invoke(new_state(ticket.text[:4000]))
                escalated += final.get("outcome") == "escalated"
                if ticket.label_category:
                    labeled_cat += 1
                    agree_cat += final.get("category") == ticket.label_category
                if ticket.label_priority:
                    labeled_pri += 1
                    agree_pri += final.get("priority") == ticket.label_priority
            report[name]["pipeline_sample"] = {
                "n": len(sample),
                "governance_mode": pipeline.mode,
                "escalation_rate": escalated / len(sample),
                "category_agreement": agree_cat / labeled_cat if labeled_cat else None,
                "priority_agreement": agree_pri / labeled_pri if labeled_pri else None,
            }
            print(f"     pipeline on {len(sample)} test tickets: {report[name]['pipeline_sample']}")

    (OUT / "public_datasets_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
