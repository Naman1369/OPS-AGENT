"""State contract tests: the fields CLAUDE.md requires must exist and be typed."""

from __future__ import annotations

from ops_agent.state import CATEGORIES, PRIORITIES, OpsAgentState, new_state, trace_event


def test_new_state_populates_identity_fields():
    state = new_state("  My laptop will not turn on.  ")
    assert state["ticket_id"].startswith("TCK-")
    assert state["raw_text"] == "My laptop will not turn on."
    assert state["submitted_at"]


def test_confidence_score_and_escalation_flag_are_defined_and_defaulted():
    """CLAUDE.md requires both to be clearly defined in the state object."""
    annotations = OpsAgentState.__annotations__
    assert "confidence_score" in annotations
    assert "escalation_flag" in annotations

    state = new_state("test")
    assert state["confidence_score"] == 0.0
    assert state["escalation_flag"] is False


def test_append_only_channels_start_empty():
    state = new_state("test")
    assert state["agent_trace"] == []
    assert state["errors"] == []


def test_explicit_ticket_id_is_respected():
    assert new_state("x", ticket_id="TCK-FIXED")["ticket_id"] == "TCK-FIXED"


def test_trace_event_shape():
    event = trace_event("intake", "triaged", {"category": "network"}, latency_ms=12.345)
    assert event["agent"] == "intake"
    assert event["event"] == "triaged"
    assert event["latency_ms"] == 12.35
    assert event["timestamp"]


def test_controlled_vocabularies():
    assert "security" in CATEGORIES and "data_loss" in CATEGORIES
    assert PRIORITIES == ("P1", "P2", "P3", "P4")
