"""Evaluation data tests: schema and ground-truth policy, cleaning, splits, adapters."""

from __future__ import annotations

import pytest

from ops_agent.data import (
    DEFAULT_DATASET_PATH,
    EvalTicket,
    load_dataset,
    normalise_text,
    policy_should_escalate,
    preprocess,
    stratified_split,
    token_jaccard,
)
from ops_agent.data.public_datasets import BUECK_PRIORITY_MAP, deduplicate, load_bueck, load_goh


# --------------------------------------------------------------------------- #
# Ground-truth policy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "category,priority,doc,adv,expected",
    [
        ("network", "P3", "KB-0001", None, (False, None)),
        ("security", "P3", "KB-0027", None, (True, "high_risk_category")),
        ("data_loss", "P2", "KB-0029", None, (True, "high_risk_category")),
        ("network", "P1", "KB-0001", "p1_outage", (True, "p1_priority")),
        ("other", "P3", None, "ambiguous", (True, "needs_clarification")),
        ("software", "P2", None, "out_of_kb", (True, "no_documented_procedure")),
        ("network", "P3", None, "multi_issue", (True, "needs_clarification")),
    ],
)
def test_escalation_ground_truth_policy(category, priority, doc, adv, expected):
    assert policy_should_escalate(category, priority, doc, adv) == expected


def test_ticket_derives_its_escalation_label():
    ticket = EvalTicket("T1", "vpn 809", "in_kb", "network", "P3", "KB-0001")
    assert ticket.should_escalate is False
    ticket = EvalTicket("T2", "phish", "in_kb", "security", "P1", "KB-0027")
    assert ticket.should_escalate is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"gold_category": "networking"},
        {"gold_priority": "P0"},
        {"subset": "other"},
        {"adversarial_type": "nonsense", "subset": "adversarial"},
        {"gold_doc_id": None},  # in_kb must name its document
    ],
)
def test_invalid_labels_are_rejected(kwargs):
    base = dict(ticket_id="T", text="x", subset="in_kb", gold_category="network", gold_priority="P3",
                gold_doc_id="KB-0001")
    base.update(kwargs)
    with pytest.raises(ValueError):
        EvalTicket(**base)


# --------------------------------------------------------------------------- #
# Cleaning
# --------------------------------------------------------------------------- #


def test_normalise_text_collapses_whitespace_and_control_chars():
    assert normalise_text("  VPN\u0007  error\n\n809 \t ") == "VPN error 809"
    assert normalise_text("ﬁle") == "file"  # NFKC ligature


def test_exact_and_near_duplicates_are_dropped():
    rows = [
        {"ticket_id": "A", "text": "VPN fails with error 809", "subset": "in_kb", "gold_category": "network",
         "gold_priority": "P3", "gold_doc_id": "KB-0001"},
        {"ticket_id": "B", "text": "vpn FAILS with error 809!", "subset": "in_kb", "gold_category": "network",
         "gold_priority": "P3", "gold_doc_id": "KB-0001"},
        {"ticket_id": "C", "text": "", "subset": "in_kb", "gold_category": "network", "gold_priority": "P3",
         "gold_doc_id": "KB-0001"},
        {"ticket_id": "D", "text": "Printer queue is stuck", "subset": "in_kb", "gold_category": "hardware",
         "gold_priority": "P3", "gold_doc_id": "KB-0015"},
    ]
    kept, report = preprocess(rows)
    assert [t.ticket_id for t in kept] == ["A", "D"]
    assert report.dropped_exact_duplicates == ["B"]
    assert report.dropped_invalid[0]["ticket_id"] == "C"


def test_token_jaccard():
    assert token_jaccard("a b c", "a b c") == 1.0
    assert token_jaccard("a b", "c d") == 0.0


# --------------------------------------------------------------------------- #
# The committed dataset and its split
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def dataset():
    if not DEFAULT_DATASET_PATH.exists():
        pytest.skip("run scripts/build_dataset.py first")
    return load_dataset()


def test_dataset_is_labeled_and_unique(dataset):
    assert len(dataset) == 430
    assert len({t.ticket_id for t in dataset}) == len(dataset)
    assert sum(t.subset == "in_kb" for t in dataset) == 300
    assert sum(t.should_escalate for t in dataset) == 170


def test_every_in_kb_ticket_points_at_a_real_article(dataset, kb_documents):
    ids = {doc.doc_id for doc in kb_documents}
    assert all(t.gold_doc_id in ids for t in dataset if t.gold_doc_id)


def test_split_is_70_15_15_disjoint_and_complete(dataset):
    split = stratified_split(dataset, seed=42)
    ids = [set(split.as_ids()[name]) for name in ("train", "calibration", "test")]
    assert sum(len(part) for part in ids) == len(dataset)
    assert not (ids[0] & ids[1]) and not (ids[0] & ids[2]) and not (ids[1] & ids[2])
    sizes = split.sizes()
    assert abs(sizes["train"] / len(dataset) - 0.70) < 0.02
    assert abs(sizes["calibration"] / len(dataset) - 0.15) < 0.02


def test_split_is_deterministic_and_seed_dependent(dataset):
    assert stratified_split(dataset, 42).as_ids() == stratified_split(dataset, 42).as_ids()
    assert stratified_split(dataset, 42).as_ids() != stratified_split(dataset, 43).as_ids()


def test_every_stratum_reaches_the_calibration_split(dataset):
    split = stratified_split(dataset, seed=42)
    strata = {t.stratum for t in dataset}
    assert {t.stratum for t in split.calibration} == strata


# --------------------------------------------------------------------------- #
# Public-dataset adapters (fixture CSVs; the real files are not redistributed)
# --------------------------------------------------------------------------- #


def test_goh_adapter_maps_topic_groups(tmp_path):
    path = tmp_path / "goh.csv"
    path.write_text("Document,Topic_group\nlaptop screen broken,Hardware\nneed admin rights,Administrative rights\n"
                    "payslip question,HR Support\n,Access\n", encoding="utf-8")
    rows = load_goh(path)
    assert [r.label_category for r in rows] == ["hardware", "access", "other"]
    assert all(r.ticket_id.startswith("GOH-") for r in rows)


def test_bueck_adapter_filters_language_and_maps_priority(tmp_path):
    path = tmp_path / "bueck.csv"
    path.write_text(
        "subject,body,answer,type,queue,priority,language\n"
        "VPN down,Cannot connect,Try again,Incident,IT Support,high,en\n"
        "Drucker,Druckt nicht,..,Incident,IT Support,low,de\n"
        "Question,How do I reset?,..,Request,IT Support,low,en\n",
        encoding="utf-8",
    )
    rows = load_bueck(path, language="en")
    assert len(rows) == 2
    assert rows[0].label_priority == BUECK_PRIORITY_MAP["high"] == "P2"
    assert rows[0].text.startswith("VPN down.")


def test_public_deduplicate(tmp_path):
    path = tmp_path / "goh.csv"
    path.write_text("Document,Topic_group\nSame text,Hardware\nsame TEXT,Hardware\n", encoding="utf-8")
    assert len(deduplicate(load_goh(path))) == 1


def test_adapter_rejects_unknown_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_goh(path)
