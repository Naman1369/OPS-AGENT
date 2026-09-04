"""Intake Agent node tests."""

from __future__ import annotations

import pytest

from ops_agent.agents.intake import intake_node
from ops_agent.state import CATEGORIES, PRIORITIES, new_state


def test_vpn_ticket_is_triaged_as_network(vpn_state, provider):
    update = intake_node(vpn_state, provider=provider)
    assert update["category"] == "network"
    assert update["priority"] in PRIORITIES
    assert update["keywords"]
    assert update["retrieval_query"]
    assert 0.0 <= update["intake_confidence"] <= 1.0


def test_error_code_is_extracted(vpn_state, provider):
    update = intake_node(vpn_state, provider=provider)
    haystack = " ".join(update["keywords"]) + " " + " ".join(str(v) for v in update["entities"].values())
    assert "809" in haystack


@pytest.mark.parametrize(
    "text,expected",
    [
        ("I received a phishing email with a suspicious link", "security"),
        ("I accidentally deleted a folder and need the data restored", "data_loss"),
        ("Outlook will not open my mailbox", "email"),
        ("My laptop battery drains in an hour", "hardware"),
        ("I am locked out of my account after a password change", "access"),
        ("The VPN will not connect over wifi", "network"),
    ],
)
def test_category_routing(text, expected, provider):
    update = intake_node(new_state(text), provider=provider)
    assert update["category"] == expected
    assert update["category"] in CATEGORIES


def test_security_and_data_loss_are_forced_to_p1(provider):
    """The category gate must not be bypassable by a low-priority triage."""
    for text in ("suspicious login and possible malware on my machine",
                 "production database was overwritten, data loss"):
        update = intake_node(new_state(text), provider=provider)
        assert update["priority"] == "P1"


def test_widespread_outage_is_p1(provider):
    update = intake_node(new_state("The entire office cannot reach the internet"), provider=provider)
    assert update["priority"] == "P1"


def test_empty_ticket_degrades_without_raising(provider):
    update = intake_node(new_state("   "), provider=provider)
    assert update["intake_confidence"] == 0.0
    assert update["errors"]
    assert update["agent_trace"][0]["event"] == "failed"


def test_node_emits_exactly_one_trace_event(vpn_state, provider):
    update = intake_node(vpn_state, provider=provider)
    assert len(update["agent_trace"]) == 1
    assert update["agent_trace"][0]["agent"] == "intake"
    assert update["agent_trace"][0]["payload"]["prompt_version"]


def test_node_returns_an_update_not_a_full_state(vpn_state, provider):
    """LangGraph nodes must return partial updates, not the whole state."""
    update = intake_node(vpn_state, provider=provider)
    assert "raw_text" not in update
    assert "ticket_id" not in update
