"""MAST labeling tests (Weeks 10-12): taxonomy, detectors, agreement."""

from __future__ import annotations

import pytest

from ops_agent.data.schema import EvalTicket
from ops_agent.llm import MockProvider
from ops_agent.mast import (
    CATEGORIES,
    FAILURE_MODES,
    MODE_CODES,
    TraceContext,
    agreement_report,
    annotate,
    cohen_kappa,
    interpret_kappa,
)
from ops_agent.mast.llm_annotator import LLMAnnotator


def test_taxonomy_has_14_modes_in_3_categories():
    assert len(FAILURE_MODES) == 14
    assert set(CATEGORIES) == {"FC1", "FC2", "FC3"}
    counts = {fc: sum(m.category == fc for m in FAILURE_MODES) for fc in CATEGORIES}
    assert counts == {"FC1": 5, "FC2": 6, "FC3": 3}
    assert all(m.definition and m.operationalisation for m in FAILURE_MODES)


def _ticket(**kw) -> EvalTicket:
    base = dict(ticket_id="T", text="vpn 809", subset="in_kb", gold_category="network",
                gold_priority="P3", gold_doc_id="KB-0001")
    base.update(kw)
    return EvalTicket(**base)


def _final(**kw) -> dict:
    final = {
        "ticket_id": "T", "raw_text": "vpn 809", "category": "network", "priority": "P3",
        "outcome": "resolved", "final_response": "x",
        "retrieved_docs": [{"doc_id": "KB-0001", "score": 0.8}],
        "draft_solution": "Fix it.", "resolution_steps": ["Do A. [KB-0001]", "Do B. [KB-0001]"],
        "citations": ["KB-0001"], "confidence_score": 0.8, "entities": {"error_code": "809"},
        "retrieval_query": "vpn 809", "governance_verdict": "SAFE_TO_RESOLVE", "escalation_flag": False,
        "agent_trace": [{"agent": a, "event": "x", "payload": {}} for a in
                        ("intake", "retrieval", "resolution", "governance", "deliver")],
    }
    final.update(kw)
    return final


def _labels(variant="naive_governed", ticket=None, **kw):
    return annotate(TraceContext(variant=variant, final=_final(**kw), ticket=ticket or _ticket()))


def test_a_clean_correct_resolution_has_no_failures():
    labels = _labels()
    assert not any(v["occurred"] for v in labels.values())


def test_wrong_document_is_task_derailment_and_incorrect_verification():
    labels = _labels(resolution_steps=["Do A. [KB-0005]"], citations=["KB-0005"],
                     retrieved_docs=[{"doc_id": "KB-0005", "score": 0.6}])
    assert labels["FM-2.3"] == {"occurred": True, "user_facing": True}
    assert labels["FM-3.3"]["occurred"] is True


def test_escalated_wrong_draft_is_derailment_that_never_reaches_the_user():
    labels = _labels(outcome="escalated", resolution_steps=["Do A. [KB-0005]"], citations=["KB-0005"],
                     governance_verdict="ESCALATE_TO_HUMAN", escalation_flag=True)
    assert labels["FM-2.3"] == {"occurred": True, "user_facing": False}
    assert labels["FM-3.3"]["occurred"] is False


def test_unverified_flawed_delivery_is_fm_3_2_not_3_3():
    ticket = _ticket(gold_category="security", gold_priority="P1", gold_doc_id="KB-0027")
    labels = _labels(variant="ungoverned", ticket=ticket, governance_verdict="UNGOVERNED",
                     resolution_steps=["Do A. [KB-0027]"], citations=["KB-0027"])
    assert labels["FM-3.2"]["occurred"] is True
    assert labels["FM-3.3"]["occurred"] is None


def test_correct_unverified_delivery_is_not_a_failure():
    labels = _labels(variant="ungoverned", governance_verdict="UNGOVERNED")
    assert labels["FM-3.2"]["occurred"] is False


def test_ambiguous_ticket_resolved_is_fail_to_ask_for_clarification():
    ticket = _ticket(subset="adversarial", adversarial_type="ambiguous", gold_doc_id=None, gold_category="other")
    assert _labels(ticket=ticket)["FM-2.2"]["occurred"] is True


def test_citation_mismatch_is_reasoning_action_mismatch():
    labels = _labels(citations=["KB-0001", "KB-0002"],
                     retrieved_docs=[{"doc_id": "KB-0001", "score": 0.8}, {"doc_id": "KB-0002", "score": 0.5}])
    assert labels["FM-2.6"]["occurred"] is True


def test_hallucinated_citation_is_ignored_input():
    trace = [{"agent": "resolution", "event": "drafted", "payload": {"hallucinated_citations": ["KB-9"]}}]
    assert _labels(agent_trace=trace)["FM-2.5"]["occurred"] is True


def test_error_code_missing_from_query_is_information_withholding():
    assert _labels(retrieval_query="vpn connection")["FM-2.4"]["occurred"] is True


def test_empty_delivery_is_premature_termination():
    labels = _labels(variant="ungoverned", draft_solution="", resolution_steps=[], citations=[],
                     confidence_score=0.0)
    assert labels["FM-3.1"]["occurred"] is True


def test_ungrounded_answer_disobeys_the_task_spec():
    labels = _labels(variant="single_agent", retrieved_docs=[{"doc_id": "KB-0001", "score": 0.1}])
    assert labels["FM-1.1"]["occurred"] is True
    assert labels["FM-1.2"]["occurred"] is None  # no roles in a single agent
    assert labels["FM-2.4"]["occurred"] is None


def test_duplicate_steps_and_backwards_traces():
    assert _labels(resolution_steps=["Do A. [KB-0001]", "do a. [KB-0001]"])["FM-1.3"]["occurred"] is True
    trace = [{"agent": a, "event": "x", "payload": {}} for a in ("intake", "retrieval", "intake", "governance")]
    assert _labels(agent_trace=trace)["FM-2.1"]["occurred"] is True


def test_missing_terminal_fields_and_no_outcome():
    final = _final()
    del final["category"]
    labels = annotate(TraceContext("naive_governed", final, _ticket()))
    assert labels["FM-1.4"]["occurred"] is True
    assert _labels(outcome=None)["FM-1.5"]["occurred"] is True


def test_every_mode_returns_bool_or_none():
    for value in _labels().values():
        assert value["occurred"] in (True, False, None)


# --------------------------------------------------------------------------- #
# Agreement
# --------------------------------------------------------------------------- #


def test_cohen_kappa_known_values():
    assert cohen_kappa([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0
    assert cohen_kappa([1, 0, 1, 0], [0, 1, 0, 1]) == -1.0
    assert cohen_kappa([1, 1, 1], [1, 1, 1]) is None
    # Balanced 2x2 table: po = 0.8, pe = 0.5 -> kappa 0.6
    a = [1] * 20 + [1] * 5 + [0] * 5 + [0] * 20
    b = [1] * 20 + [0] * 5 + [1] * 5 + [0] * 20
    assert cohen_kappa(a, b) == pytest.approx(0.6)
    # Unbalanced: po = 0.7, pa = 0.7, pb = 0.6 -> pe = 0.54 -> kappa = 0.16 / 0.46
    a = [1] * 25 + [1] * 10 + [0] * 5 + [0] * 10
    b = [1] * 25 + [0] * 10 + [1] * 5 + [0] * 10
    assert cohen_kappa(a, b) == pytest.approx(0.16 / 0.46)


def test_interpretation_bands():
    assert interpret_kappa(0.85) == "almost perfect"
    assert interpret_kappa(0.5) == "moderate"
    assert interpret_kappa(None).startswith("undefined")


def test_agreement_report_per_mode_and_pooled():
    a = [{code: False for code in MODE_CODES} for _ in range(4)]
    b = [dict(row) for row in a]
    a[0]["FM-2.3"] = b[0]["FM-2.3"] = True
    report = agreement_report(a, b, MODE_CODES)
    assert report["per_mode"]["FM-2.3"]["kappa"] == 1.0
    assert report["pooled_kappa"] == 1.0


def test_llm_annotator_refuses_the_mock_provider():
    with pytest.raises(ValueError):
        LLMAnnotator(MockProvider())


def test_llm_annotator_parses_a_real_style_response():
    class FakeJudge:
        name, model = "fake", "judge"

        def generate_json(self, prompt, **kwargs):
            assert "FM-3.3" in kwargs["system"]
            return {"labels": {"FM-2.3": True}, "evidence": {"FM-2.3": "wrong doc"}}, None

    result = LLMAnnotator(FakeJudge()).annotate(_final(), _ticket())
    assert result["labels"]["FM-2.3"] is True
    assert set(result["labels"]) == set(MODE_CODES)
