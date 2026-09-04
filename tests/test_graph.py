"""LangGraph compile and end-to-end state-transition tests.

Per CLAUDE.md these run after the per-agent node tests: the individual agents
must be correct before the assembled graph is judged.
"""

from __future__ import annotations

import pytest

from ops_agent.config import GovernanceSettings, Settings
from ops_agent.graph import (
    build_graph,
    compile_pipeline,
    route_after_governance,
    route_after_intake,
    route_after_retrieval,
)
from ops_agent.state import new_state


# --------------------------------------------------------------------------- #
# Routing functions in isolation
# --------------------------------------------------------------------------- #


def test_route_after_intake_proceeds_when_a_query_exists():
    assert route_after_intake({"retrieval_query": "vpn 809", "intake_confidence": 0.8}) == "retrieval"


def test_route_after_intake_skips_retrieval_without_a_query():
    assert route_after_intake({"retrieval_query": "", "intake_confidence": 0.8}) == "governance"


def test_route_after_intake_skips_retrieval_when_triage_failed():
    assert route_after_intake({"retrieval_query": "x", "intake_confidence": 0.0}) == "governance"


def test_route_after_retrieval_enforces_grounding():
    assert route_after_retrieval({"grounded": True}) == "resolution"
    assert route_after_retrieval({"grounded": False}) == "governance"


def test_route_after_governance_gates_delivery():
    assert route_after_governance(
        {"governance_verdict": "SAFE_TO_RESOLVE", "escalation_flag": False}
    ) == "deliver"
    assert route_after_governance(
        {"governance_verdict": "ESCALATE_TO_HUMAN", "escalation_flag": True}
    ) == "escalate"
    assert route_after_governance({"governance_verdict": "BLOCKED", "escalation_flag": True}) == "escalate"


def test_governance_verdict_and_flag_cannot_disagree():
    """A stale SAFE verdict with the flag raised must still escalate."""
    assert route_after_governance(
        {"governance_verdict": "SAFE_TO_RESOLVE", "escalation_flag": True}
    ) == "escalate"


# --------------------------------------------------------------------------- #
# Compilation and topology
# --------------------------------------------------------------------------- #


def test_graph_compiles():
    assert compile_pipeline() is not None


def test_graph_contains_all_six_nodes():
    nodes = set(build_graph().nodes)
    assert {"intake", "retrieval", "resolution", "governance", "deliver", "escalate"} <= nodes


# --------------------------------------------------------------------------- #
# End-to-end state transitions
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def pipeline():
    return compile_pipeline()


def _path(final: dict) -> list[str]:
    return [event["agent"] for event in final.get("agent_trace", [])]


def test_state_flows_through_all_four_agents(pipeline):
    final = pipeline.invoke(new_state("Outlook hangs on loading profile and will not start."))
    assert _path(final)[:4] == ["intake", "retrieval", "resolution", "governance"]


def test_no_data_is_lost_between_nodes(pipeline):
    final = pipeline.invoke(new_state("The printer queues jobs but nothing ever prints."))
    for field in (
        "ticket_id", "raw_text", "category", "priority", "keywords",
        "retrieved_docs", "draft_solution", "confidence_score",
        "escalation_flag", "governance_verdict", "final_response", "outcome",
    ):
        assert field in final, f"{field} was lost in transit"


def test_every_run_reaches_a_terminal_node(pipeline):
    for ticket in (
        "VPN error 809 will not connect",
        "I clicked a link in a phishing email",
        "Purple.",
        "The entire office has no internet",
    ):
        final = pipeline.invoke(new_state(ticket))
        assert final["outcome"] in {"resolved", "escalated"}
        assert final["final_response"]


def test_governance_is_on_every_path(pipeline):
    for ticket in ("VPN error 809", "Purple.", "I deleted a folder by accident"):
        assert "governance" in _path(pipeline.invoke(new_state(ticket)))


def test_ungrounded_ticket_never_reaches_the_resolution_agent(pipeline):
    """The grounding rule is enforced by topology, not by prompt wording."""
    final = pipeline.invoke(new_state("Purple."))
    assert "resolution" not in _path(final)
    assert final["escalation_flag"] is True


def test_security_ticket_escalates_regardless_of_confidence(pipeline):
    final = pipeline.invoke(new_state("I received a phishing email and entered my password."))
    assert final["category"] == "security"
    assert final["escalation_flag"] is True
    assert final["policy_checks"]["G6_category_gate"] is False


def test_p1_outage_escalates(pipeline):
    final = pipeline.invoke(new_state("The entire office cannot reach the internet, nobody can work."))
    assert final["priority"] == "P1"
    assert final["escalation_flag"] is True


def test_escalation_response_carries_the_reasons_and_the_draft(pipeline):
    final = pipeline.invoke(new_state("I clicked a link in a phishing email."))
    assert "ESCALATED TO A HUMAN ENGINEER" in final["final_response"]
    assert final["governance_reasons"]
    for reason in final["governance_reasons"]:
        assert reason.split(":")[0] in final["final_response"]


def test_trace_is_append_only_and_ordered(pipeline):
    final = pipeline.invoke(new_state("Outlook will not open my mailbox."))
    trace = final["agent_trace"]
    assert len(trace) >= 4
    timestamps = [event["timestamp"] for event in trace]
    assert timestamps == sorted(timestamps)
    assert all(event.get("agent") and event.get("event") for event in trace)


def test_pipeline_is_deterministic_under_the_mock_provider(pipeline):
    ticket = "VPN fails to connect with error 809 on Windows 11."
    first = pipeline.invoke(new_state(ticket, ticket_id="TCK-DET"))
    second = pipeline.invoke(new_state(ticket, ticket_id="TCK-DET"))
    for field in ("category", "priority", "confidence_score", "governance_verdict",
                  "escalation_flag", "citations", "outcome"):
        assert first[field] == second[field]


def test_deliver_path_runs_end_to_end(pipeline, monkeypatch):
    """Exercise the autonomous-resolution branch.

    Retrieval scores depend on which embedder is installed, so rather than
    depending on a particular similarity value this test relaxes the confidence
    threshold and asserts the deliver branch behaves correctly when reached.
    """
    import ops_agent.agents.governance as gov

    relaxed = GovernanceSettings()
    object.__setattr__(relaxed, "confidence_threshold", 0.05)
    monkeypatch.setattr(gov, "SETTINGS", Settings(governance=relaxed))

    final = pipeline.invoke(new_state("VPN fails to connect with error 809 behind NAT."))
    assert final["governance_verdict"] == "SAFE_TO_RESOLVE"
    assert final["escalation_flag"] is False
    assert final["outcome"] == "resolved"
    assert _path(final)[-1] == "deliver"
    assert "Recommended steps:" in final["final_response"]
    assert "Sources:" in final["final_response"]
    for citation in final["citations"]:
        assert citation in final["final_response"]


def test_a_strict_threshold_closes_the_deliver_path(pipeline, monkeypatch):
    """The gate must be able to shut: nothing is delivered at threshold 1.0."""
    import ops_agent.agents.governance as gov

    strict = GovernanceSettings()
    object.__setattr__(strict, "confidence_threshold", 1.0)
    monkeypatch.setattr(gov, "SETTINGS", Settings(governance=strict))

    final = pipeline.invoke(new_state("VPN fails to connect with error 809 behind NAT."))
    assert final["outcome"] == "escalated"


def test_confidence_score_stays_uncalibrated_at_this_milestone(pipeline):
    """Week 5-7 scope guard: raw confidence only, no calibration in the trace."""
    final = pipeline.invoke(new_state("VPN error 809"))
    for event in final["agent_trace"]:
        if "confidence_is_calibrated" in event.get("payload", {}):
            assert event["payload"]["confidence_is_calibrated"] is False
