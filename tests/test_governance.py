"""Governance Agent tests -- the deterministic gate, check by check."""

from __future__ import annotations

from ops_agent.agents.governance import (
    BLOCKED,
    ESCALATE_TO_HUMAN,
    SAFE_TO_RESOLVE,
    governance_node,
)
from ops_agent.config import GovernanceSettings
from ops_agent.state import RetrievedDoc, new_state


def passing_state(**overrides) -> dict:
    """A state that passes every check; individual tests break one at a time."""
    state = new_state("User cannot connect to the VPN, error code 809")
    state.update(
        {
            "category": "network",
            "priority": "P3",
            "intake_confidence": 0.85,
            "grounded": True,
            "top_relevance": 0.86,
            "retrieved_docs": [
                RetrievedDoc(doc_id="KB-0001", title="VPN Error 809", content="body",
                             score=0.86, rank=1, source="test", category="network")
            ],
            "draft_solution": "Enable NAT traversal.",
            "resolution_steps": ["Set the registry value. [KB-0001]"],
            "citations": ["KB-0001"],
            "confidence_score": 0.88,
            "errors": [],
        }
    )
    state.update(overrides)
    return state


def test_all_checks_passing_yields_safe_to_resolve(governance_settings):
    update = governance_node(passing_state(), settings=governance_settings)
    assert update["governance_verdict"] == SAFE_TO_RESOLVE
    assert update["escalation_flag"] is False
    assert all(update["policy_checks"].values())


def test_seven_checks_are_always_evaluated(governance_settings):
    update = governance_node(passing_state(), settings=governance_settings)
    assert set(update["policy_checks"]) == {
        "G1_grounded", "G2_cited", "G3_confident", "G4_complete",
        "G5_priority_gate", "G6_category_gate", "G7_intake_clarity",
    }


def test_g1_ungrounded_is_blocked(governance_settings):
    update = governance_node(
        passing_state(grounded=False, retrieved_docs=[], draft_solution="", resolution_steps=[]),
        settings=governance_settings,
    )
    assert update["policy_checks"]["G1_grounded"] is False
    assert update["governance_verdict"] == BLOCKED
    assert update["escalation_flag"] is True


def test_g2_missing_citations_escalates(governance_settings):
    update = governance_node(passing_state(citations=[]), settings=governance_settings)
    assert update["policy_checks"]["G2_cited"] is False
    assert update["escalation_flag"] is True


def test_g2_citation_to_an_unretrieved_document_escalates(governance_settings):
    update = governance_node(passing_state(citations=["KB-9999"]), settings=governance_settings)
    assert update["policy_checks"]["G2_cited"] is False
    assert any("never retrieved" in reason for reason in update["governance_reasons"])


def test_g3_below_threshold_escalates(governance_settings):
    below = governance_settings.confidence_threshold - 0.01
    update = governance_node(passing_state(confidence_score=below), settings=governance_settings)
    assert update["policy_checks"]["G3_confident"] is False
    assert update["governance_verdict"] == ESCALATE_TO_HUMAN


def test_g3_exactly_at_threshold_passes(governance_settings):
    update = governance_node(
        passing_state(confidence_score=governance_settings.confidence_threshold),
        settings=governance_settings,
    )
    assert update["policy_checks"]["G3_confident"] is True


def test_g4_incomplete_answer_escalates(governance_settings):
    update = governance_node(passing_state(resolution_steps=[]), settings=governance_settings)
    assert update["policy_checks"]["G4_complete"] is False


def test_g5_p1_always_escalates_however_confident(governance_settings):
    update = governance_node(
        passing_state(priority="P1", confidence_score=0.99), settings=governance_settings
    )
    assert update["policy_checks"]["G5_priority_gate"] is False
    assert update["escalation_flag"] is True


def test_g6_security_always_escalates_however_confident(governance_settings):
    update = governance_node(
        passing_state(category="security", priority="P2", confidence_score=0.99),
        settings=governance_settings,
    )
    assert update["policy_checks"]["G6_category_gate"] is False
    assert update["escalation_flag"] is True


def test_g6_data_loss_always_escalates(governance_settings):
    update = governance_node(
        passing_state(category="data_loss", priority="P2", confidence_score=0.99),
        settings=governance_settings,
    )
    assert update["policy_checks"]["G6_category_gate"] is False


def test_g7_ambiguous_intake_escalates(governance_settings):
    update = governance_node(passing_state(intake_confidence=0.05), settings=governance_settings)
    assert update["policy_checks"]["G7_intake_clarity"] is False


def test_threshold_is_configurable(governance_settings):
    strict = GovernanceSettings()
    object.__setattr__(strict, "confidence_threshold", 0.95)
    assert governance_node(passing_state(), settings=strict)["escalation_flag"] is True


def test_decision_is_deterministic(governance_settings):
    state = passing_state()
    first = governance_node(state, settings=governance_settings)
    second = governance_node(state, settings=governance_settings)
    assert first["policy_checks"] == second["policy_checks"]
    assert first["governance_verdict"] == second["governance_verdict"]
    assert first["governance_reasons"] == second["governance_reasons"]


def test_every_escalation_records_a_reason(governance_settings):
    update = governance_node(passing_state(confidence_score=0.1), settings=governance_settings)
    assert update["governance_reasons"]
    assert update["escalation_flag"] is True


def test_trace_records_the_threshold_in_force(governance_settings):
    payload = governance_node(passing_state(), settings=governance_settings)["agent_trace"][0]["payload"]
    assert payload["confidence_threshold"] == governance_settings.confidence_threshold
    assert payload["confidence_is_calibrated"] is False
    assert payload["policy_version"]


def test_governance_does_not_call_an_llm(monkeypatch, governance_settings):
    """The gate must stay deterministic; any LLM call here is a design violation."""
    import ops_agent.llm.factory as factory

    def explode(*args, **kwargs):
        raise AssertionError("Governance must not invoke an LLM provider.")

    monkeypatch.setattr(factory, "get_provider", explode)
    assert governance_node(passing_state(), settings=governance_settings)["governance_verdict"]
