"""Evaluation harness tests (Weeks 13-14): outcomes, variants, replay, stats, metrics."""

from __future__ import annotations

import numpy as np
import pytest

from ops_agent.calibration import CalibrationProfile
from ops_agent.data.schema import EvalTicket
from ops_agent.evaluation.baselines import build_single_agent_graph, build_ungoverned_graph
from ops_agent.evaluation.harness import Harness, fit_profile, gold_resolution_texts, run_fingerprint
from ops_agent.evaluation.metrics import projected_cost, rouge_l_f1, summarize
from ops_agent.evaluation.outcomes import (
    answer_correct,
    outcome_class,
    primary_citation,
    step_citations,
)
from ops_agent.evaluation.replay import replay
from ops_agent.evaluation.stats import (
    bootstrap_ci,
    cochran_q,
    holm,
    mcnemar_exact,
    paired_bootstrap_diff,
    wilson_interval,
)
from ops_agent.evaluation.tracking import Tracker
from ops_agent.state import new_state


def _ticket(**kw) -> EvalTicket:
    base = dict(ticket_id="T", text="VPN error 809 behind NAT", subset="in_kb", gold_category="network",
                gold_priority="P3", gold_doc_id="KB-0001")
    base.update(kw)
    return EvalTicket(**base)


# --------------------------------------------------------------------------- #
# Outcome definitions
# --------------------------------------------------------------------------- #


def test_primary_citation_is_the_most_cited_document():
    final = {"resolution_steps": ["a [KB-0002]", "b [KB-0001]", "c [KB-0001]"], "citations": ["KB-0002"]}
    assert step_citations(final["resolution_steps"]) == ["KB-0002", "KB-0001", "KB-0001"]
    assert primary_citation(final) == "KB-0001"


@pytest.mark.parametrize(
    "outcome,steps,ticket_kw,expected",
    [
        ("resolved", ["a [KB-0001]"], {}, "correct_resolution"),
        ("resolved", ["a [KB-0004]"], {}, "unsafe_resolution"),
        ("resolved", ["a [KB-0027]"], {"gold_category": "security", "gold_priority": "P1", "gold_doc_id": "KB-0027"},
         "unsafe_resolution"),
        ("escalated", ["a [KB-0001]"], {}, "unnecessary_escalation"),
        ("escalated", ["a [KB-0004]"], {}, "necessary_escalation"),
        ("escalated", [], {}, "necessary_escalation"),
    ],
)
def test_outcome_classes(outcome, steps, ticket_kw, expected):
    final = {"outcome": outcome, "draft_solution": "x" if steps else "", "resolution_steps": steps}
    assert outcome_class(final, _ticket(**ticket_kw)) == expected


def test_no_documented_fix_means_no_correct_answer():
    ticket = _ticket(subset="adversarial", adversarial_type="out_of_kb", gold_doc_id=None, gold_category="other")
    assert not answer_correct({"draft_solution": "x", "resolution_steps": ["a [KB-0001]"]}, ticket)


# --------------------------------------------------------------------------- #
# Baseline variants run end to end
# --------------------------------------------------------------------------- #


def test_single_agent_baseline_retrieves_answers_and_self_gates(store):
    final = build_single_agent_graph(store=store).compile().invoke(new_state("VPN error 809 behind NAT at home"))
    assert [e["agent"] for e in final["agent_trace"]][0] == "single_agent"
    assert final["retrieved_docs"] and final["draft_solution"]
    assert final["governance_verdict"].startswith("SELF_ASSESSED")
    assert final["outcome"] in ("resolved", "escalated")


def test_ungoverned_variant_always_delivers(store):
    graph = build_ungoverned_graph().compile()
    for text in ("I clicked a link in a phishing email", "Purple."):
        final = graph.invoke(new_state(text))
        assert final["outcome"] == "resolved"
        assert "governance" not in [e["agent"] for e in final["agent_trace"]]


# --------------------------------------------------------------------------- #
# Harness, calibration fitting and replay
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def tickets():
    from ops_agent.data import DEFAULT_DATASET_PATH, load_dataset

    if not DEFAULT_DATASET_PATH.exists():
        pytest.skip("run scripts/build_dataset.py first")
    data = load_dataset()
    return data[:100] + data[-20:]  # in-KB and adversarial tickets


@pytest.fixture(scope="module")
def harness(store):
    return Harness(store, gold_resolution_texts())


def test_harness_records_have_the_fields_the_metrics_need(harness, tickets):
    records = harness.run("naive_governed", tickets[:5])
    for record in records:
        for key in ("outcome_class", "confidence_raw", "eligible_except_g3", "mast", "rouge_l", "needs_human"):
            assert key in record
        assert len(record["mast"]) == 14


def test_fit_profile_and_replay_match_a_real_calibrated_run(harness, tickets):
    v3 = harness.run("naive_governed", tickets)
    profile, diagnostics = fit_profile(v3, run_fingerprint(harness.store), alpha=0.2, delta=0.2)
    assert isinstance(profile, CalibrationProfile) and profile.temperature > 0
    assert diagnostics["n_answered"] >= 10
    v4 = harness.run("calibration_governed", tickets, profile)
    replayed = {r["ticket_id"]: r["delivered"] for r in replay(v3, profile)}
    assert all(replayed[r["ticket_id"]] == r["delivered"] for r in v4)


def test_summarize_reports_every_metric_family(harness, tickets):
    summary = summarize(harness.run("single_agent", tickets[:8]))
    for key in ("automation_rate", "unsafe_resolution_rate", "escalation", "resolution_quality",
                "classification", "calibration", "mast", "cost", "latency_ms"):
        assert key in summary
    assert sum(summary["outcomes"].values()) == summary["n"]


def test_rouge_l():
    assert rouge_l_f1("restart the print spooler", "restart the print spooler") == 1.0
    assert rouge_l_f1("", "anything") == 0.0
    assert 0.0 < rouge_l_f1("restart spooler service", "restart the print spooler service") < 1.0


def test_projected_cost():
    assert projected_cost(1_000_000, 0) == pytest.approx(0.75)


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #


def test_mcnemar_exact():
    a = [1] * 10 + [0] * 10
    b = [0] * 10 + [0] * 10
    result = mcnemar_exact(a, b)
    assert result["only_first"] == 10 and result["only_second"] == 0
    assert result["p_value"] == pytest.approx(2 * 0.5 ** 10)
    assert mcnemar_exact([1, 0], [1, 0])["p_value"] == 1.0


def test_cochran_q_detects_a_difference_and_ignores_none():
    x = np.array([[1, 0, 0]] * 15 + [[0, 0, 0]] * 5)
    assert cochran_q(x)["p_value"] < 0.001
    assert cochran_q(np.ones((5, 3)))["p_value"] == 1.0


def test_holm_is_monotone_and_capped():
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert max(holm([0.9, 0.8])) <= 1.0


def test_bootstrap_and_wilson_intervals_contain_the_estimate():
    low, high = bootstrap_ci([0, 1] * 50, seed=1)
    assert low < 0.5 < high
    low, high = wilson_interval(10, 100)
    assert low < 0.1 < high
    diff = paired_bootstrap_diff([1, 1, 0, 0], [0, 0, 0, 0])
    assert diff["difference"] == 0.5


def test_tracker_is_a_noop_when_disabled():
    assert Tracker(enabled=False).log_run("x", {}) is False
